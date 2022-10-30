import sys
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
from numpy.random import shuffle
import threading


logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s: %(message)s')
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
web.minimize_window()
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
        # self.song_lists 的下标
        self.cur_song_list_index = -1
        self.cur_playing_song_id = -1
        # 是否正在播放歌单
        self.is_playing_song_list = False

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

    # 解析歌曲时长，输出秒数
    @staticmethod
    def parseSongLen(duration_str):
        assert len(duration_str.split(':')) == 2
        minutes = int(duration_str.split(':')[0])
        seconds = int(duration_str.split(':')[1])
        return 60 * minutes + seconds

    def getMusicUrls(self):
        # 网易云音乐需要先进入iframe
        with self.getIntoIframe(self.xpath_dict['search_result_frame'], self.search_directly):
            self.waitElement(self.xpath_dict['search_result_list'], "result_list")
            music_list = web.find_elements(By.XPATH, self.xpath_dict['search_result_list'])
            if music_list:
                self.cur_search_result = []
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
                    'duration': self.parseSongLen(duration),
                })

    # 回放搜索结果
    def showSearchResult(self):
        if not self.cur_search_result:
            print("please search first")
            return
        for i, song_info in enumerate(self.cur_search_result):
            singer = song_info['singer']
            title = song_info['title']
            song_url = song_info['song_url']
            print(f"{i} singer: {singer}\ttitle: {title}\turl: {song_url}")

    def playMusicByUrl(self, song_url):
        self.openUrl(song_url)
        try:
            WebDriverWait(web, 2).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/video"))
            )
            print("start playing!")
            return True
        except TimeoutException:
            print(f"Could not play. This song may need VIP.")
            return False

    def checkValidIndex(self, index):
        if index >= len(self.song_lists):
            print(f"please input valid index, range between 0 ~ {len(self.cur_search_result)-1}")
            return False
        return True

    def playMusicBySongInfo(self, song_info):
        singer = song_info['singer']
        title = song_info['title']
        true_url = song_info['true_url']
        duration = song_info['duration']
        if self.playMusicByUrl(true_url):
            print(f"playing: {singer} - {title} , duration is {duration} s")
            return True
        return False

    def playMusicByIndex(self, index):
        if not self.cur_search_result:
            print("currently no searching result, please search song first")
            return
        if self.checkValidIndex(index):
            true_song_url = self.cur_search_result[index]['true_url']
            self.playMusicByUrl(true_song_url)

    def stopMusic(self):
        self.openUrl(self.home_page)
        self.is_playing_song_list = False
        print("stop!")

    @staticmethod
    def getUserSongLists():
        # 读取yaml文件
        with open(user_song_lists_fp, 'r', encoding="utf-8") as f:
            data = yaml.load(stream=f, Loader=yaml.FullLoader)
            if data is None:
                return []
            return data

    @property
    def songListNameList(self):
        return [_['song_list_name'] for _ in self.song_lists]

    def saveUserSongLists(self):
        with open(user_song_lists_fp, 'w', encoding="utf-8") as f:
            yaml.dump(self.song_lists, stream=f, Dumper=yaml.Dumper)

    def createSongList(self, song_list_name):
        if song_list_name in self.songListNameList:
            print("name already exists, please use another name")
        else:
            self.song_lists.append({
                'song_list_name': song_list_name,
                'song_list': [],
            })
            self.saveUserSongLists()
            print(f"success! songList {song_list_name} is created")

    def _getSongListIndex(self, index):
        if index == -1:
            if self.cur_song_list_index >= 0:
                return self.cur_song_list_index
            else:
                print("please select a songList first")
                return None
        if index >= len(self.song_lists) or index < -1:
            print(f"index={index} is out of range 0 ~ {len(self.song_lists) - 1}")
            return None
        return index

    def selectSongList(self, index):
        index = self._getSongListIndex(index)
        if index is not None:
            self.cur_song_list_index = index
            print(f"songList {self.song_lists[index]['song_list_name']} is selected")
            return True
        else:
            return False

    def initCurSongList(self):
        self.cur_song_list_index = -1

    def deleteSongList(self, index=-1):
        index = self._getSongListIndex(index)
        if index is not None:
            input_str = input("Are you sure to delete? Enter y to confirm: ")
            if input_str in ['y', 'Y']:
                self.song_lists = self.song_lists[0:index] + self.song_lists[index+1:]
                if index == self.cur_song_list_index:
                    self.initCurSongList()
                elif index < self.cur_song_list_index:
                    self.cur_song_list_index -= 1
                self.saveUserSongLists()
                print("delete songList success!")

    def showAllSongListName(self):
        if not self.song_lists:
            print("find no songList")
            return
        print("all songLists:")
        for i, song_list_name in enumerate(self.songListNameList):
            print(i, song_list_name)

    def showAllSongInSongList(self, index=-1):
        index = self._getSongListIndex(index)
        if index is not None:
            if not self.song_lists[index]:
                print("find no song in current songList")
            else:
                print(f"find {len(self.song_lists[index]['song_list'])} songs in songList "
                      f"{self.song_lists[index]['song_list_name']}: ")
                for i, song_info in enumerate(self.song_lists[index]['song_list']):
                    singer = song_info['singer']
                    title = song_info['title']
                    print(f"{i} singer: {singer}\ttitle: {title}")

    def deleteSongInSongList(self, song_id, index=-1):
        index = self._getSongListIndex(index)
        if index is not None:
            if song_id >= len(self.song_lists[index]['song_list']):
                print(f"please input valid index, range between 0 ~ {len(self.song_lists[index]['song_list'])-1}")
                return False
            singer = self.song_lists[index]['song_list'][song_id]['singer']
            title = self.song_lists[index]['song_list'][song_id]['title']
            print(f"you are trying to delete：singer: {singer}\ttitle: {title}")
            input_str = input("Are you sure to delete? Enter y to confirm: ")
            if input_str in ['y', 'Y']:
                self.song_lists[index]['song_list'] = self.song_lists[index]['song_list'][:song_id] + \
                                                  self.song_lists[index]['song_list'][song_id+1:]
                if index == self.cur_song_list_index:
                    if song_id == self.cur_playing_song_id:
                        self.cur_playing_song_id = -1
                    elif song_id < self.cur_playing_song_id:
                        self.cur_playing_song_id -= 1
                self.saveUserSongLists()
                print("delete song success!")
                return True
        return False

    def addSongToSongList(self, song_id, index=-1):
        index = self._getSongListIndex(index)
        if index is not None:
            if song_id >= len(self.cur_search_result):
                print(f"please input valid index, range between 0 ~ {len(self.cur_search_result)-1}")
                return
            song_url = self.cur_search_result[song_id]['song_url']
            singer = self.cur_search_result[song_id]['singer']
            title = self.cur_search_result[song_id]['title']
            if song_url in [song_info['song_url'] for song_info in self.song_lists[index]['song_list']]:
                print(f"song is already exist in songList {self.song_lists[index]['song_list_name']}")
                return
            self.song_lists[index]['song_list'].append(self.cur_search_result[song_id])
            self.saveUserSongLists()
            print(f"success!  {singer} - {title} is added to songList {self.song_lists[index]['song_list_name']}")

    def playSongList(self, index=-1, mod='normal'):
        assert mod in play_mods
        self.is_playing_song_list = True
        index = self._getSongListIndex(index)
        if index is not None:
            play_list = self.song_lists[index]['song_list'][:]
            if mod == 'random':
                shuffle(play_list)
            for song_info in play_list:
                if not self.is_playing_song_list:
                    return
                duration = song_info['duration']
                if self.playMusicBySongInfo(song_info):
                    time.sleep(duration)


class MusicConsoleUI:
    def __init__(self):
        print("=￣ω￣=  WELCOME TO FIND FISH STATION FOR MUSIC")
        self.music_console = MusicConsole('net_ease')
        self.is_running = True
        self.cmd_ctrl_tbl = []
        self.registerCmd()
        # 线程任务
        self.task_play_song_list = None
        self.task_play_song_list_rdm = None
        self.runUI()

    @staticmethod
    def getValidCmd(cmd_input):
        if not cmd_input.isdigit():
            print("please enter a valid number")
            return -1
        else:
            return int(cmd_input)

    def registerCmd(self):
        self.cmd_ctrl_tbl = [
            # 搜索模式
            {
                "cmd_type": "search and play",
                "cmd_list": [
                    ["search", self.search],
                    ["play", self.playSearchResultByIndex],
                    ["stop", self.stop],
                    ["show", self.showSearchResult],
                    ["exit", self.exit_],
                ]
            },
            # 歌单模式
            {
                "cmd_type": "songList mod",
                "cmd_list": [
                    ["select", self.selectSongList],
                    ["play_cur", self.playSongList],
                    ["play_cur_rdm", self.playSongListRandom],
                    ["del_cur", self.delCurSongList],
                    ["show_cur", self.showCurSongList],
                    ["show_all", self.showAllSongList],
                    ["create_new", self.createSongList],
                ]
            },
            # 歌曲操作
            {
                "cmd_type": "song opts",
                "cmd_list": [
                    ["add_song", self.addSongByIndex],
                    ["delete_song", self.deleteSongById],
                ]
            },
        ]

    def printCmdTbl(self):
        print("*" * 60 + " cmd table " + "*" * 60)
        i = 0
        for cmb_ctrl in self.cmd_ctrl_tbl:
            cmd_type = cmb_ctrl["cmd_type"]
            cmd_list = cmb_ctrl["cmd_list"]
            text_temp = cmd_type + "\t>>\t"
            for cmd_info in cmd_list:
                cmd_name, handle = cmd_info
                text_temp += f"[{i}] {cmd_name}\t"
                i += 1
            print(text_temp)

    def doCmd(self, cmd_input):
        cmd = self.getValidCmd(cmd_input)
        i = 0
        if cmd >= 0:
            for cmb_ctrl in self.cmd_ctrl_tbl:
                cmd_list = cmb_ctrl["cmd_list"]
                for cmd_info in cmd_list:
                    cmd_name, handle = cmd_info
                    if cmd == i:
                        handle()
                        return
                    else:
                        i += 1
        print("cmd id out of range!")

    def runUI(self):
        while self.is_running:
            self.printCmdTbl()
            cmd_input = input("please input cmd id: ")
            self.doCmd(cmd_input)

    def search(self):
        keyword = ""
        while not keyword:
            keyword = input("please input keyword: ")
        if keyword == '-1':
            return
        self.music_console.searchMusic(keyword)
        self.music_console.getMusicUrls()

    def playSearchResultByIndex(self):
        index = input("please input id of song in searching result: ")
        index = self.getValidCmd(index)
        self.music_console.playMusicByIndex(index)

    def stop(self):
        self.music_console.stopMusic()

    def exit_(self):
        self.is_running = False
        self.music_console.stopMusic()
        sys.exit()

    def showAllSongList(self):
        self.music_console.showAllSongListName()

    def selectSongList(self):
        if self.music_console.song_lists:
            self.showAllSongList()
            song_list_id = input("please input id of songList: ")
            song_list_id = self.getValidCmd(song_list_id)
            if song_list_id >= 0:
                self.music_console.selectSongList(song_list_id)
        else:
            print("no songList exist")

    def showCurSongList(self):
        self.music_console.showAllSongInSongList()

    def delCurSongList(self):
        self.music_console.deleteSongList()

    def createSongList(self):
        song_list_name = input("please input name of songList: ")
        self.music_console.createSongList(song_list_name)

    def showSearchResult(self):
        self.music_console.showSearchResult()

    def addSongByIndex(self):
        self.showSearchResult()
        search_res_id = input("please input id of song: ")
        search_res_id = self.getValidCmd(search_res_id)
        if search_res_id >= 0:
            self.music_console.addSongToSongList(search_res_id)

    def deleteSongById(self):
        self.showCurSongList()
        song_id = input("please input id of song: ")
        song_id = self.getValidCmd(song_id)
        if song_id >= 0:
            self.music_console.deleteSongInSongList(song_id)

    def playSongList(self):
        self.task_play_song_list = threading.Thread(target=self.music_console.playSongList)
        self.task_play_song_list.start()
        time.sleep(1)

    def playSongListRandom(self):
        self.task_play_song_list_rdm = threading.Thread(target=self.music_console.playSongList,
                                                        kwargs={'mod': 'random'})
        self.task_play_song_list_rdm.start()
        time.sleep(1)


if __name__ == '__main__':
    # mc = MusicConsole('net_ease')
    # mc.searchMusic("fripside")
    # mc.getMusicUrls()
    # # mc.playMusicByUrl("http://music.163.com/song/media/outer/url?id=4919477")
    # mc.playMusicByIndex(5)
    # time.sleep(5)
    # mc.stopMusic()
    # mc.createUserSongList("Abc")
    # mc.createUserSongList("Abc")
    # mc.createUserSongList("Abc2")
    MusicConsoleUI()



















