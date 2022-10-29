import json
import re
import os
import yaml
import time
import logging
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from selenium.webdriver.common.keys import Keys
from contextlib import contextmanager
from selenium.webdriver import ActionChains
import pyautogui
from numpy.random import shuffle


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
console_logger = logging.getLogger(__name__)
# 用户歌单信息路径
user_song_lists_fn = "song_lists.yaml"
user_song_lists_fp = os.path.join(os.path.dirname(__file__), user_song_lists_fn).replace('\\', '/')
# 读取yaml文件
cfg_fn = "console_config.yaml"
cfg_fp = os.path.join(os.path.dirname(__file__), cfg_fn).replace('\\', '/')
with open(cfg_fp, 'r', encoding="utf-8") as f:
    cfg_data = yaml.load(stream=f, Loader=yaml.FullLoader)

chrome_options = Options()
# chrome_options.add_argument('--headless')

web = Chrome(options=chrome_options)

music_station = cfg_data['music_station']

# 播放模式
play_mods = ['normal', 'random']


class MusicConsole:
    def __init__(self, station='net_ease'):
        assert station in music_station
        self.station = station
        self.music_station_url = music_station[station]['url']
        self.true_url_tpl = music_station[station]['true_url']
        self.xpath_dict = music_station[station]['xpath']
        self.home_page = music_station[station]['home_page']
        # 是否需要在搜索结果页面进入iframe
        self.search_directly = 'search_result_frame' not in self.xpath_dict
        self.song_xpath = self.xpath_dict['song']
        self.cur_search_result = []
        self.song_lists = self.getUserSongLists()
        self.cur_song_list = []

    @staticmethod
    def openUrl(url):
        try:
            web.get(url)
        except TimeoutException:
            raise TimeoutException(f"page loads fail: {url}")

    @staticmethod
    def waitElement(xpath, info=""):
        try:
            WebDriverWait(web, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            console_logger.info(f"element {info} loads fail! {xpath}")
        except TimeoutException:
            raise TimeoutException(f"element {info} loads fail, please try again. xpath: {xpath}")

    # 进入iframe，最后自动退出
    @contextmanager
    def getIntoIframe(self, iframe_xpath, do_nothing):
        if do_nothing:
            return
        frame_ele = web.find_element(By.XPATH, iframe_xpath)
        web.switch_to.frame(frame_ele)
        yield
        web.switch_to.default_content()

    def searchMusic(self, keyword):
        url = self.music_station_url.replace("$keyword$", keyword)
        self.openUrl(url)
        # 网易云音乐需要先进入iframe
        with self.getIntoIframe(self.xpath_dict['search_result_frame'], self.search_directly):
            self.waitElement(self.xpath_dict['search_result_num'], "result_num")
            num_rst = web.find_element(By.XPATH, self.xpath_dict['search_result_num']).text
        print(f"find {num_rst} results")

    def getMusicUrls(self):
        # 网易云音乐需要先进入iframe
        with self.getIntoIframe(self.xpath_dict['search_result_frame'], self.search_directly):
            self.waitElement(self.xpath_dict['search_result_list'], "result_list")
            music_list = web.find_elements(By.XPATH, self.xpath_dict['search_result_list'])
            for i, song_div in enumerate(music_list):
                title = song_div.find_element(By.XPATH, self.song_xpath['title']).get_attribute('title')
                singer_xpath = self.song_xpath['singer']
                while singer_xpath:
                    try:
                        singer = song_div.find_element(By.XPATH, singer_xpath).text
                        break
                    except NoSuchElementException:
                        singer_xpath = "/".join(singer_xpath.split('/')[:-1])
                song_url = song_div.find_element(By.XPATH, self.song_xpath['song_url']).get_attribute('href')
                duration = song_div.find_element(By.XPATH, self.song_xpath['duration']).text
                print(f"{i} singer: {singer}\ttitle: {title}\turl: {song_url}")
                song_id = song_url.split('id=')[-1]
                self.cur_search_result.append({
                    'singer': singer,
                    'title': title,
                    'song_url': song_url,
                    'song_id': song_id,
                    'true_url': self.true_url_tpl.replace("$song_id$", song_id),
                    'duration': duration,
                })

    def playMusicByUrl(self, song_url):
        self.openUrl(song_url)
        try:
            WebDriverWait(web, 2).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/video"))
            )
            print("start playing! {singer} - {title}")
            return True
        except TimeoutException:
            print("Could not play. This song may need VIP")
            return False

    def checkValidIndex(self, index):
        if index >= len(self.cur_search_result):
            print(f"please input valid index, range between 0 ~ {len(self.cur_search_result)-1}")
            return False
        return True

    def playMusicByIndex(self, index):
        if not self.cur_search_result:
            print("currently no searching result, please search song first")
            return
        if self.checkValidIndex(index):
            true_song_url = self.cur_search_result[index]['true_url']
            self.playMusicByUrl(true_song_url)

    def stopMusic(self):
        self.openUrl(self.home_page)
        print("stop!")

    @staticmethod
    def getUserSongLists():
        # 读取yaml文件
        with open(user_song_lists_fp, 'r', encoding="utf-8") as f:
            data = yaml.load(stream=f, Loader=yaml.FullLoader)
            if data is None:
                return {}
            return data

    def saveUserSongLists(self):
        with open(user_song_lists_fp, 'w', encoding="utf-8") as f:
            yaml.dump(self.song_lists, stream=f, Dumper=yaml.Dumper)

    def createUserSongList(self, song_list_name):
        if song_list_name in self.song_lists:
            print("name already exists, please use another name")
        else:
            self.song_lists[song_list_name] = []
        self.saveUserSongLists()

    def checkSongListExist(self, song_list_name):
        if song_list_name not in self.song_lists:
            print("songList no exist!")
            return False
        return True

    def selectSongList(self, song_list_name):
        if self.checkSongListExist(song_list_name):
            self.cur_song_list = self.song_lists[song_list_name]

    def delUserSongList(self, song_list_name):
        if self.checkSongListExist(song_list_name):
            input_str = input("Are you sure to delete? Enter y to confirm: ")
            if input_str in ['y', 'Y']:
                del self.song_lists[song_list_name]
                self.saveUserSongLists()

    def showAllUserSongList(self):
        if not self.song_lists:
            print("find no songList")
            return
        for song_list in self.song_lists:
            print("all songLists:")
            print(song_list)

    def showAllSongInSongList(self, song_list_name):
        if self.checkSongListExist(song_list_name):
            if not self.song_lists[song_list_name]:
                print("find no song in current songList")
                return
            print(f"共 {len(self.song_lists[song_list_name])} 首歌曲：")
            for i, song_info in enumerate(self.song_lists[song_list_name]):
                singer = song_info['singer']
                title = song_info['title']
                print(f"{i} singer: {singer}\ttitle: {title}")

    def delSongToSongList(self, index, song_list_name):
        if self.checkSongListExist(song_list_name):
            if index >= len(self.song_lists[song_list_name]):
                print(f"please input valid index, range between 0 ~ {len(self.song_lists[song_list_name])-1}")
                return
            singer = self.song_lists[song_list_name][index]['singer']
            title = self.song_lists[song_list_name][index]['title']
            print(f"you are trying to delete：singer: {singer}\ttitle: {title}")
            input_str = input("Are you sure to delete? Enter y to confirm: ")
            if input_str in ['y', 'Y']:
                self.song_lists[song_list_name] = self.song_lists[song_list_name][:index] + \
                                                  self.song_lists[song_list_name][index+1:]
                self.saveUserSongLists()

    def addSongToSongList(self, index, song_list_name):
        if self.checkSongListExist(song_list_name) and self.checkValidIndex(index):
            self.song_lists[song_list_name].append(self.cur_search_result[index])
            singer = self.cur_search_result[index]['singer']
            title = self.cur_search_result[index]['title']
            print(f"success!  {singer} - {title} is added to {song_list_name}")
            self.saveUserSongLists()

    def playSongList(self, song_list_name, mod='normal'):
        assert mod in play_mods
        play_list = self.song_lists[song_list_name][:]
        if mod == 'random':
            shuffle(play_list)
        for song_info in play_list:
            singer = song_info['singer']
            title = song_info['title']
            true_url = song_info['true_url']
            duration = song_info['duration']
            if self.playMusicByUrl(true_url):
                try:
                    time.sleep(duration)
                except KeyboardInterrupt:
                    self.stopMusic()


class MusicConsoleUI:
    def __init__(self):
        print("************ WELCOME TO FIND FISH STATION ************")

    # 打印初始命令提示
    def printBasicCmd(self):
        print("1:search 2:play 3:stop 4:select songList")

    # 歌单模式的命令提示
    def printBasicCmd(self):
        print("1:search 2:play 3:stop 4:select songList 5: ")


if __name__ == '__main__':
    mc = MusicConsole('net_ease')
    mc.searchMusic("fripside")
    # mc.getMusicUrls()
    # # mc.playMusicByUrl("http://music.163.com/song/media/outer/url?id=4919477")
    # mc.playMusicByIndex(5)
    # time.sleep(5)
    # mc.stopMusic()
    # mc.createUserSongList("Abc")
    # mc.createUserSongList("Abc")
    # mc.createUserSongList("Abc2")



















