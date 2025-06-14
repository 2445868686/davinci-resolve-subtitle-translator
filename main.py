#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取字幕 → 逐行并发翻译 → 生成译文 SRT
现已支持多服务商：OpenAI  /  Azure
"""

# ================= 用户配置 =================
SCRIPT_NAME    = "DaVinci Translator "
SCRIPT_VERSION = "v0.1"           # ↑ 版本号顺延
SCRIPT_AUTHOR  = "HEIBA"

# 界面尺寸
SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080
WINDOW_WIDTH, WINDOW_HEIGHT = 400, 500
X_CENTER = (SCREEN_WIDTH - WINDOW_WIDTH) // 2
Y_CENTER = (SCREEN_HEIGHT - WINDOW_HEIGHT) // 2

# 赞助或帮助链接
SCRIPT_KOFI_URL = "https://ko-fi.com/heiba"
SCRIPT_WX_URL   = "https://mp.weixin.qq.com/s?__biz=MzUzMTk2MDU5Nw==&mid=2247484626&idx=1&sn=e5eef7e48fbfbf37f208ed9a26c5475a"

# 并发与重试
CONCURRENCY = 10
MAX_RETRY   = 3
TIMEOUT     = 30

# OpenAI 默认信息（可在 GUI 中覆盖）
OPENAI_DEFAULT_KEY   = ""
OPENAI_DEFAULT_URL   = ""
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

# Azure 默认信息（可在 GUI 中覆盖）
AZURE_DEFAULT_KEY    = "BhD5f8aAsNRsVdYYschy54sGdVPGqwKEiOsebzZbRS6u5WUqTIl0JQQJ99BFACYeBjFXJ3w3AAAbACOGdZI3"
AZURE_DEFAULT_REGION = "eastus"
AZURE_DEFAULT_URL    = "https://api.cognitive.microsofttranslator.com"
# ===========================================
#   语言名称 → Azure Translator 代码映射表
# ===========================================
LANG_CODE_MAP = {
    "中文（普通话）": "zh-Hans",
    "中文（粤语）":   "yue",
    "English":      "en",
    "Japanese":     "ja",
    "Korean":       "ko",
    "Spanish":      "es",
    "Portuguese":   "pt",
    "French":       "fr",
    "Indonesian":   "id",
    "German":       "de",
    "Russian":      "ru",
    "Italian":      "it",
    "Arabic":       "ar",
    "Turkish":      "tr",
    "Ukrainian":    "uk",
    "Vietnamese":   "vi",
    "Dutch":        "nl",
}
GOOGLE_LANG_CODE_MAP = {
    "中文（普通话）": "zh-cn",
    "中文（粤语）":   "yue",      # google 对粤语支持有限，如失败可改 'zh-tw'
    "English":      "en",
    "Japanese":     "ja",
    "Korean":       "ko",
    "Spanish":      "es",
    "Portuguese":   "pt",
    "French":       "fr",
    "Indonesian":   "id",
    "German":       "de",
    "Russian":      "ru",
    "Italian":      "it",
    "Arabic":       "ar",
    "Turkish":      "tr",
    "Ukrainian":    "uk",
    "Vietnamese":   "vi",
    "Dutch":        "nl",
}
# ===========================================

import os, re,sys, json, time, tempfile, platform, requests, concurrent.futures
from functools import partial
from abc import ABC, abstractmethod
from googletrans import Translator 
script_path = os.path.dirname(os.path.abspath(sys.argv[0]))
config_dir = os.path.join(script_path, 'config')
settings_file = os.path.join(config_dir, 'translator_settings.json')

# --------- 1  Provider 基类与两家实现 ---------
class BaseProvider(ABC):
    """所有翻译服务商抽象基类"""
    name = "base"
    def __init__(self, cfg: dict):
        self.cfg = cfg
    @abstractmethod
    def translate(self, text: str, target_lang: str) -> str:
        pass

# ---------- Google 翻译 ----------
class GoogleProvider(BaseProvider):
    name = "google"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.translator = Translator(
            service_urls=cfg.get("service_urls", 
            [
                "translate.google.com",
                "translate.google.com.hk",
                "translate.google.com.tw",
            ]),
        )

    def translate(self, text, target_lang):
        """
        target_lang 需为 googletrans 语言代码，如 'zh-cn' / 'en'
        """
        for attempt in range(1, self.cfg.get("max_retry", 3) + 1):
            try:
                res = self.translator.translate(
                    text, dest=target_lang)       # 不再传 timeout
                return res.text
            except Exception as e:
                if attempt == self.cfg.get("max_retry", 3):
                    raise
                time.sleep(2 ** attempt)

                
# ---------- OpenAI ----------
class OpenAIProvider(BaseProvider):
    name = "openai"
    def translate(self, text, target_lang):
        payload = {
            "model": self.cfg["model"],
            "messages": [
                {"role": "system",
                 "content": f"You are a translation engine. "
                            f"Translate the user message into {target_lang}. "
                            f"Return ONLY the translated sentence."},
                {"role": "user", "content": text}
            ],
            "temperature": 0
        }
        headers = {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type":  "application/json"
        }
        url = self.cfg["base_url"].rstrip("/") + "/v1/chat/completions"

        for attempt in range(1, self.cfg.get("max_retry", 3)+1):
            try:
                r = requests.post(url, headers=headers, json=payload,
                                  timeout=self.cfg.get("timeout", 30))
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt == self.cfg.get("max_retry", 3):
                    raise
                time.sleep(2 ** attempt)

# ---------- Azure Translator ----------
class AzureProvider(BaseProvider):
    name = "azure"
    def translate(self, text, target_lang):
        params  = {"api-version": "3.0", "to": target_lang}
        headers = {
            "Ocp-Apim-Subscription-Key": self.cfg["api_key"],
            "Ocp-Apim-Subscription-Region": self.cfg["region"],
            "Content-Type": "application/json"
        }
        url  = self.cfg["base_url"].rstrip("/") + "/translate"
        body = [{"text": text}]

        for attempt in range(1, self.cfg.get("max_retry", 3)+1):
            try:
                r = requests.post(url, params=params, headers=headers,
                                  json=body, timeout=self.cfg.get("timeout", 15))
                r.raise_for_status()
                return r.json()[0]["translations"][0]["text"]
            except Exception as e:
                if attempt == self.cfg.get("max_retry", 3):
                    raise
                time.sleep(2 ** attempt)

# --------- 2  ProviderManager 单文件实现 ---------
class ProviderManager:
    def __init__(self, cfg: dict):
        self._providers = {}
        self.default = cfg.get("default")
        for name, p_cfg in cfg["providers"].items():
            cls = globals()[p_cfg["class"]]      # 直接从当前模块拿类
            self._providers[name] = cls(p_cfg)
    def list(self):            # 返回支持的服务商列表
        return list(self._providers.keys())
    def get(self, name=None):  # 获取指定服务商实例
        return self._providers[name or self.default]

# --------- 3  服务商配置（可在 GUI 动态修改后写回） ---------
PROVIDERS_CFG = {
    "default": "google",
    "providers": {
        "google": {               # ← 新增
            "class": "GoogleProvider",
            "service_urls": ["translate.google.com"],  # 可多填备用域名
            "max_retry": MAX_RETRY,
            "timeout": 10
        },
        "azure": {
            "class":  "AzureProvider",
            "base_url": AZURE_DEFAULT_URL,
            "api_key":  AZURE_DEFAULT_KEY,
            "region":   AZURE_DEFAULT_REGION,
            "max_retry": MAX_RETRY,
            "timeout":  15
        },
        "openai": {
            "class": "OpenAIProvider",
            "base_url": OPENAI_DEFAULT_URL,
            "api_key":  OPENAI_DEFAULT_KEY,
            "model":    OPENAI_DEFAULT_MODEL,
            "max_retry": MAX_RETRY,
            "timeout":  TIMEOUT
        },
    }
}

prov_manager = ProviderManager(PROVIDERS_CFG)   # 实例化

# ================== DaVinci Resolve 接入 ==================
try:
    import DaVinciResolveScript as dvr_script
    from python_get_resolve import GetResolve
except ImportError:
    # mac / windows 常规路径补全
    if platform.system() == "Darwin": 
        path1 = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Examples"
        path2 = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    elif platform.system() == "Windows":
        path1 = os.path.join(os.environ['PROGRAMDATA'], "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Examples")
        path2 = os.path.join(os.environ['PROGRAMDATA'], "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Modules")
    else:
        raise EnvironmentError("Unsupported operating system")
    sys.path += [path1, path2]
    import DaVinciResolveScript as dvr_script
    from python_get_resolve import GetResolve

resolve = GetResolve()
ui       = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

# -------------------- 4  GUI 搭建 --------------------
win = dispatcher.AddWindow(
    {
        "ID": 'MyWin',
        "WindowTitle": SCRIPT_NAME + SCRIPT_VERSION,
        "Geometry": [X_CENTER, Y_CENTER, WINDOW_WIDTH, WINDOW_HEIGHT],
        "Spacing": 10,
        "StyleSheet": "*{font-size:14px;}"
    },
    [
        ui.VGroup([
            ui.TabBar({"ID":"MyTabs","Weight":0.0}),
            ui.Stack({"ID":"MyStack","Weight":1.0},[
                # ===== 4.1 翻译页 =====
                ui.VGroup({"Weight":1},[
                    ui.TextEdit({"ID":"SubTxt","Text":"","ReadOnly":False,"Weight":1}),
                    ui.Label({"ID":"TargetLangLabel","Text":"目标语言","Weight":0.1}),
                    ui.ComboBox({"ID":"TargetLangCombo","Weight":0.1}),
                    ui.Label({"ID": "StatusLabel", "Text": " ", "Alignment": {"AlignHCenter": True, "AlignVCenter": True},"Weight":0.1}),
                    ui.Button({"ID":"TransButton","Text":"翻译","Weight":0.1}),
                ]),
                # ===== 4.2 配置页 =====
                ui.VGroup({"Weight":1},[
                    ui.Label({"ID":"ProviderLabel","Text":"服务商","Weight":0.1}),
                    ui.ComboBox({"ID":"ProviderCombo","Weight":0.1}),
                    ui.HGroup({"Weight": 0.1}, [
                        ui.Label({"Text": "Azure", "Alignment": {"AlignLeft": True}, "Weight": 0.1}),
                        ui.Button({"ID": "ShowAzure", "Text": "配置","Weight": 0.1,}),
                    ]),
                    ui.HGroup({"Weight":0.1},[
                        ui.Label({"Text":"OpenAI","Weight":0.1}),
                        ui.Button({"ID":"ShowOpenAI","Text":"配置","Weight":0.1}),
                    ]),
                    
                    ui.HGroup({"Weight":0.1},[
                        ui.CheckBox({"ID":"LangEnCheckBox","Text":"EN","Checked":True,"Weight":0}),
                        ui.CheckBox({"ID":"LangCnCheckBox","Text":"简体中文","Checked":False,"Weight":1}),
                    ]),
                    ui.TextEdit({"ID":"infoTxt","Text":"","ReadOnly":True,"Weight":1}),
                ])
            ])
        ])
    ]
)

# --- OpenAI 单独配置窗口（维持原有） ---
# openai配置窗口
openai_config_window = dispatcher.AddWindow(
    {
        "ID": "OpenAIConfigWin",
        "WindowTitle": "OpenAI API",
        "Geometry": [X_CENTER, Y_CENTER, 400, 250],
        "Hidden": True,
        "StyleSheet": """
        * {
            font-size: 14px; /* 全局字体大小 */
        }
    """
    },
    [
        ui.VGroup(
            [
                ui.Label({"ID": "OpenAILabel","Text": "填写OpenAI API信息", "Alignment": {"AlignHCenter": True, "AlignVCenter": True}}),

                ui.Label({"ID": "OpenAIBaseURLLabel", "Text": "Base URL", "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                ui.LineEdit({"ID": "OpenAIBaseURL", "Text":"","PlaceholderText": "https://api.openai.com/v1", "Weight": 0.8}),
                ui.Label({"ID": "OpenAIApiKeyLabel", "Text": "密钥", "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                ui.LineEdit({"ID": "OpenAIApiKey", "Text": "", "EchoMode": "Password", "Weight": 0.8}),
                ui.Label({"ID":"OpenAIModelLabel","Text":"模型","Weight":0.1}),
                ui.ComboBox({"ID":"OpenAIModelCombo","Weight":0.1}),   
                ui.HGroup({"Weight": 1}, [
                    ui.Button({"ID": "OpenAIConfirm", "Text": "确定","Weight": 1}),
                    ui.Button({"ID": "OpenAIRegisterButton", "Text": "注册","Weight": 1}),
                ]),
                
            ]
        )
    ]
)

# azure配置窗口
azure_config_window = dispatcher.AddWindow(
    {
        "ID": "AzureConfigWin",
        "WindowTitle": "Azure API",
        "Geometry": [X_CENTER, Y_CENTER, 400, 200],
        "Hidden": True,
        "StyleSheet": """
        * {
            font-size: 14px; /* 全局字体大小 */
        }
    """
    },
    [
        ui.VGroup(
            [
                ui.Label({"ID": "AzureLabel","Text": "填写Azure API信息", "Alignment": {"AlignHCenter": True, "AlignVCenter": True}}),
                ui.HGroup({"Weight": 1}, [
                    ui.Label({"ID": "AzureRegionLabel", "Text": "区域", "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                    ui.LineEdit({"ID": "AzureRegion", "Text": "", "Weight": 0.8}),
                ]),
                ui.HGroup({"Weight": 1}, [
                    ui.Label({"ID": "AzureApiKeyLabel", "Text": "密钥", "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                    ui.LineEdit({"ID": "AzureApiKey", "Text": "", "EchoMode": "Password", "Weight": 0.8}),
                    
                ]),
                ui.HGroup({"Weight": 1}, [
                    ui.Button({"ID": "AzureConfirm", "Text": "确定","Weight": 1}),
                    ui.Button({"ID": "AzureRegisterButton", "Text": "注册","Weight": 1}),
                ]),
                
            ]
        )
    ]
)

translations = {
    "cn": {
        "Tabs": ["翻译","配置"],
        "OpenAIModelLabel":"模型：",
        "TargetLangLabel":"目标语音：",
        "TransButton":"开始翻译",
        "ShowAzure":"配置",
        "ShowOpenAI": "配置",
        "ProviderLabel":"服务商",
        "AzureRegionLabel":"区域",
        "AzureApiKeyLabel":"密钥",
        "AzureConfirm":"确定",
        "AzureRegisterButton":"注册",
        "OpenAILabel":"填写OpenAI API信息",
        "OpenAIBaseURLLabel":"Base URL",
        "OpenAIApiKeyLabel":"密钥",
        "OpenAIConfirm":"确定",
        "OpenAIRegisterButton":"注册",
        
    },

    "en": {
        "Tabs": ["Translator", "Configuration"],
        "OpenAIModelLabel":"Model:",
        "TargetLangLabel":"Target Language:",
        "TransButton":"Translate",
        "ShowAzure":"Config",
        "ShowOpenAI": "Config",
        "ProviderLabel":"Provider",
        "AzureRegionLabel":"Region",
        "AzureApiKeyLabel":"Key",
        "AzureConfirm":"OK",
        "AzureRegisterButton":"Register",
        "OpenAILabel":"OpenAI API",
        "OpenAIBaseURLLabel":"Base URL",
        "OpenAIApiKeyLabel":"Key",
        "OpenAIConfirm":"OK",
        "OpenAIRegisterButton":"Register",
        
    }
}    

items       = win.GetItems()
openai_items = openai_config_window.GetItems()
azure_items = azure_config_window.GetItems()
items["MyStack"].CurrentIndex = 0

# --- 4.3 初始化下拉内容 ---
for tab_name in translations["cn"]["Tabs"]:
    items["MyTabs"].AddTab(tab_name)

for p in prov_manager.list():
    items["ProviderCombo"].AddItem(p)
items["ProviderCombo"].CurrentText = PROVIDERS_CFG["default"]

openai_models = ["gpt-4o-mini","gpt-4o","gpt-4.1-nano","gpt-4.1",]
for model in openai_models:
    openai_items["OpenAIModelCombo"].AddItem(model)

target_language = [
    "中文（普通话）", "中文（粤语）", "English", "Japanese", "Korean",
    "Spanish", "Portuguese", "French", "Indonesian", "German", "Russian",
    "Italian", "Arabic", "Turkish", "Ukrainian", "Vietnamese", "Dutch"
]

for lang in target_language:
    items["TargetLangCombo"].AddItem(lang)  
    
def check_or_create_file(file_path):
    if os.path.exists(file_path):
        pass
    else:
        try:
            with open(file_path, 'w') as file:
                json.dump({}, file)  
        except IOError:
            raise Exception(f"Cannot create file: {file_path}")
        
def save_settings(settings, settings_file):
    with open(settings_file, 'w') as file:
        content = json.dumps(settings, indent=4)
        file.write(content)
        
def load_settings(settings_file):
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            content = file.read()
            if content:
                try:
                    settings = json.loads(content)
                    return settings
                except json.JSONDecodeError as err:
                    print('Error decoding settings:', err)
                    return None
    return None

default_settings = {
    "AZURE_API_KEY":"",
    "AZURE_REGION":"",
    "OPENAI_API_KEY": "",
    "PROVIDER":0,
    "OPENAI_BASE_URL": "",
    "OPENAI_MODEL": 0,
    "TARGET_LANG":0,
    "CN":True,
    "EN":False,
}

check_or_create_file(settings_file)
saved_settings = load_settings(settings_file) 

def switch_language(lang):
    """
    根据 lang (可取 'cn' 或 'en') 切换所有控件的文本
    """
    if "MyTabs" in items:
        for index, new_name in enumerate(translations[lang]["Tabs"]):
            items["MyTabs"].SetTabText(index, new_name)

    for item_id, text_value in translations[lang].items():
        # 确保 items[item_id] 存在，否则会报 KeyError
        if item_id == "Tabs":
            continue
        if item_id in items:
            items[item_id].Text = text_value
        elif item_id in azure_items:    
            azure_items[item_id].Text = text_value
        elif item_id in openai_items:    
            openai_items[item_id].Text = text_value
        else:
            print(f"[Warning] items 中不存在 ID 为 {item_id} 的控件，无法设置文本！")

    # 缓存复选框状态
    checked = items["LangEnCheckBox"].Checked



def on_cn_checkbox_clicked(ev):
    items["LangEnCheckBox"].Checked = not items["LangCnCheckBox"].Checked
    if items["LangEnCheckBox"].Checked:
        switch_language("en")
        print("en")
    else:
        print("cn")
        switch_language("cn")
win.On.LangCnCheckBox.Clicked = on_cn_checkbox_clicked

def on_en_checkbox_clicked(ev):
    items["LangCnCheckBox"].Checked = not items["LangEnCheckBox"].Checked
    if items["LangEnCheckBox"].Checked:
        switch_language("en")
        print("en")
    else:
        print("cn")
        switch_language("cn")
win.On.LangEnCheckBox.Clicked = on_en_checkbox_clicked


if saved_settings:
    openai_items["OpenAIModelCombo"].CurrentIndex = saved_settings.get("OPENAI_MODEL", default_settings["OPENAI_MODEL"])
    items["TargetLangCombo"].CurrentIndex = saved_settings.get("TARGET_LANG", default_settings["TARGET_LANG"])
    items["LangCnCheckBox"].Checked = saved_settings.get("CN", default_settings["CN"])
    items["LangEnCheckBox"].Checked = saved_settings.get("EN", default_settings["EN"])
    items["ProviderCombo"].CurrentIndex = saved_settings.get("PROVIDER", default_settings["PROVIDER"])
    openai_items["OpenAIApiKey"].Text = saved_settings.get("OPENAI_API_KEY", default_settings["OPENAI_API_KEY"])
    openai_items["OpenAIBaseURL"].Text = saved_settings.get("OPENAI_BASE_URL", default_settings["OPENAI_BASE_URL"])    

if items["LangEnCheckBox"].Checked :
    switch_language("en")
else:
    switch_language("cn")

def close_and_save(settings_file):
    settings = {

        "CN":items["LangCnCheckBox"].Checked,
        "EN":items["LangEnCheckBox"].Checked,
        "PROVIDER":items["ProviderCombo"].CurrentIndex,
        "AZURE_API_KEY":azure_items["AzureApiKey"].Text,
        "AZURE_REGION":azure_items["AzureRegion"].Text,
        
        "OPENAI_API_KEY": openai_items["OpenAIApiKey"].Text,
        "OPENAI_BASE_URL": openai_items["OpenAIBaseURL"].Text,
        "OPENAI_MODEL": openai_items["OpenAIModelCombo"].CurrentIndex,
        "TARGET_LANG":items["TargetLangCombo"].CurrentIndex,


    }

    save_settings(settings, settings_file)
# --- 4.4 Tab 切换 ---
def on_my_tabs_current_changed(ev):
    items["MyStack"].CurrentIndex = ev["Index"]
win.On.MyTabs.CurrentChanged = on_my_tabs_current_changed

# --- 4.5 打开 OpenAI 配置窗 ---
def on_show_openai(ev):
    openai_config_window.Show()
win.On.ShowOpenAI.Clicked = on_show_openai

def on_openai_close(ev):
    print("OpenAI API 配置完成")
    openai_config_window.Hide()
openai_config_window.On.OpenAIConfirm.Clicked = on_openai_close
openai_config_window.On.OpenAIConfigWin.Close = on_openai_close


# --- 4.6 打开 Azure 配置窗 ---
def on_show_azure(ev):
    azure_config_window.Show()
win.On.ShowAzure.Clicked = on_show_azure

def on_azure_close(ev):
    print("Azure API 配置完成")
    azure_config_window.Hide()
azure_config_window.On.AzureConfirm.Clicked = on_azure_close
azure_config_window.On.AzureConfigWin.Close = on_azure_close

def on_azure_register_link_button_clicked(ev):
    ...
azure_config_window.On.AzureRegisterButton.Clicked = on_azure_register_link_button_clicked


# =============== 5  Resolve 辅助函数 ===============
def connect_resolve():
    resolve = dvr_script.scriptapp("Resolve")
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    media_pool = project.GetMediaPool(); 
    root_folder = media_pool.GetRootFolder()
    timeline      = project.GetCurrentTimeline()
    fps     = float(project.GetSetting("timelineFrameRate"))
    return resolve, project, media_pool,root_folder,timeline, fps

def get_subtitles(timeline):
    subs = []
    for tidx in range(1, timeline.GetTrackCount("subtitle")+1):
        if not timeline.GetIsTrackEnabled("subtitle", tidx):
            continue
        for item in timeline.GetItemListInTrack("subtitle", tidx):
            subs.append({"start":item.GetStart(),
                         "end":item.GetEnd(),
                         "text":item.GetName()})
    return subs

def frame_to_timecode(frame, fps):
    sec      = frame / fps
    h, rem   = divmod(sec, 3600)
    m, rem   = divmod(rem, 60)
    s, msec  = divmod(rem, 1)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int(msec*1000):03}"

def write_srt(subs, start_frame, fps, timeline_name, lang_code, output_dir="."):
    """
    按 [时间线名称]_[语言code]_[4位随机码]_[版本].srt 规则写文件：
      1. 安全化时间线名称和语言code
      2. 添加4位随机码
      3. 扫描已有文件，计算新版本号
      4. 写入并返回路径
    """
    # 1. 安全化名称
    safe_name = re.sub(r'[\\\/:*?"<>|]', "_", timeline_name)
    safe_lang = re.sub(r'[\\\/:*?"<>|]', "_", lang_code)
    import random
    import string
    # 2. 生成4位随机字母+数字码
    rand_code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

    # 3. 创建目录（若不存在）
    os.makedirs(output_dir, exist_ok=True)

    # 4. 扫描已有版本
    pattern = re.compile(
        rf"^{re.escape(safe_name)}_{re.escape(safe_lang)}_{re.escape(rand_code)}_(\d+)\.srt$"
    )
    versions = []
    for fname in os.listdir(output_dir):
        m = pattern.match(fname)
        if m:
            versions.append(int(m.group(1)))
    version = max(versions) + 1 if versions else 1

    # 5. 构造文件名与路径
    filename = f"{safe_name}_{safe_lang}_{rand_code}_{version}.srt"
    path = os.path.join(output_dir, filename)

    # 6. 写入 SRT 内容
    with open(path, "w", encoding="utf-8") as f:
        for idx, s in enumerate(subs, 1):
            f.write(
                f"{idx}\n"
                f"{frame_to_timecode(s['start'] - start_frame, fps)} --> "
                f"{frame_to_timecode(s['end'] - start_frame, fps)}\n"
                f"{s['text']}\n\n"
            )

    return path

def import_srt_to_first_empty(path):
    resolve, current_project,current_media_pool,current_root_folder, current_timeline, fps = connect_resolve()
    if not current_timeline: return False
    # 1. 禁用所有现有字幕轨
    states = {}
    for i in range(1, current_timeline.GetTrackCount("subtitle")+1):
        states[i] = current_timeline.GetIsTrackEnabled("subtitle", i)
        if states[i]: current_timeline.SetTrackEnable("subtitle", i, False)
    # 2. 找第一条空轨，没有就新建
    target = next((i for i in range(1, current_timeline.GetTrackCount("subtitle")+1)
                   if not current_timeline.GetItemListInTrack("subtitle", i)), None)
    if target is None:
        current_timeline.AddTrack("subtitle")
        target = current_timeline.GetTrackCount("subtitle")
    current_timeline.SetTrackEnable("subtitle", target, True)
    # 3. 导入
    current_media_pool.SetCurrentFolder(current_root_folder)
    current_media_pool.ImportMedia([path])
    current_media_pool.AppendToTimeline([current_root_folder.GetClipList()[-1]])
    print("🎉 字幕已导入并落在轨道 #", target)
    return True

# =============== 6  并发翻译封装 ===============
def translate_parallel(text_list, provider, lang_for_provider, status_label=None):
    """
    并发翻译封装，支持不同服务商调用，以及可选的状态回调
    :param text_list: 待翻译文本列表
    :param provider: BaseProvider 子类实例
    :param lang_for_provider: 传入 provider.translate 的语言参数，如自然语言名称或语言代码
    :param status_label: 可选的 GUI 状态标签控件，用于实时更新进度
    :return: 翻译后文本列表
    """
    total = len(text_list)
    result = [None] * total
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        # 提交任务，动态传入 lang_for_provider
        futures = {pool.submit(provider.translate, t, lang_for_provider): idx
                   for idx, t in enumerate(text_list)}

        for f in concurrent.futures.as_completed(futures):
            idx = futures[f]
            try:
                result[idx] = f.result()
            except Exception as e:
                result[idx] = f"[失败: {e}]"
            finally:
                completed += 1
                if status_label:
                    pct = int(completed / total * 100)
                    status_label.Text = f"翻译中… {pct}% ({completed}/{total})"

    return result

# =============== 7  主按钮逻辑 ===============
def on_trans_clicked(ev):
    resolve, current_project,current_media_pool, current_root_folder,current_timeline, fps = connect_resolve()
    subs = get_subtitles(current_timeline)
    if not subs:
        print("❌ 没有找到字幕块"); return

    # 把原字幕显示在 TextEdit 里
    items["SubTxt"].Text = "\n\n".join(
        f"{i+1}\n{frame_to_timecode(s['start'],fps)} --> {frame_to_timecode(s['end'],fps)}\n{s['text']}"
        for i,s in enumerate(subs)
    )

    # 取 GUI 参数
    provider_name = items["ProviderCombo"].CurrentText
    provider      = prov_manager.get(provider_name)
    target_lang_name = items["TargetLangCombo"].CurrentText        # 例：中文（普通话）

    # 如果用户在 GUI 修改了 key/url/model，则写回 provider.cfg
    lang_for_provider = None
    if provider_name == "openai":
        provider.cfg["api_key"]  = openai_items["OpenAIApiKey"].Text or provider.cfg["api_key"]
        provider.cfg["base_url"] = openai_items["OpenAIBaseURL"].Text or provider.cfg["base_url"]
        provider.cfg["model"]    = openai_items["OpenAIModelCombo"].CurrentText or provider.cfg["model"]
        # OpenAI uses the full language name in its prompt
        lang_for_provider = target_lang_name

    elif provider_name == "azure":
        provider.cfg["api_key"] = azure_items["AzureApiKey"].Text or AZURE_DEFAULT_KEY
        provider.cfg["region"]  = azure_items["AzureRegion"].Text or AZURE_DEFAULT_REGION
        # Azure uses codes like "zh-Hans"
        lang_for_provider = LANG_CODE_MAP.get(target_lang_name)

    elif provider_name == "google":
        # Google uses codes like "zh-cn"
        lang_for_provider = GOOGLE_LANG_CODE_MAP.get(target_lang_name)

    else:
        items["StatusLabel"].Text = f"Error: Unknown provider '{provider_name}'"
        print(f"❌ Unknown provider selected: {provider_name}")
        return # Stop execution if provider is not recognized

    total = len(subs)

    # 禁用按钮，避免重复点击
    items["TransButton"].Enabled = False
    # 初始化百分比
    items["StatusLabel"].Text = "翻译中… 0% (0/{})".format(total)

    ori_texts = [s["text"] for s in subs]
    
    trans_texts = translate_parallel(ori_texts, provider, lang_for_provider, items["StatusLabel"])
           
    for s, new in zip(subs, trans_texts):
        s["text"] = new

    output_dir = os.path.join(script_path, 'srt')

    srt_path = write_srt(
        subs,
        current_timeline.GetStartFrame(),
        fps,
        current_timeline.GetName(),
        lang_for_provider,  # 你之前得出的 target_lang_code
        output_dir=output_dir
    )
    print("✅ 翻译完成，SRT 路径：", srt_path)

    # 4. 导入并判断是否成功
    succeed = import_srt_to_first_empty(srt_path)

    # 5. 如果成功，就删除本地 .srt
    if succeed:
        try:
            items["StatusLabel"].Text = "翻译完成！"
        except Exception as e:
            items["StatusLabel"].Text = "翻译失败！"
            
    items["TransButton"].Enabled = True
win.On.TransButton.Clicked = on_trans_clicked

# =============== 8  关闭窗口保存设置 ===============
def on_close(ev):
    import shutil
    output_dir = os.path.join(script_path, 'srt')
    if os.path.exists(output_dir):
        try:
            shutil.rmtree(output_dir)  # ✅ 删除整个文件夹及其中内容
            print(f"🧹 已删除文件夹：{output_dir}")
        except Exception as e:
            print(f"⚠️ 删除文件夹失败：{e}")
    close_and_save(settings_file)
    dispatcher.ExitLoop()

win.On.MyWin.Close = on_close

# =============== 9  运行 GUI ===============
win.Show(); 
dispatcher.RunLoop(); 
win.Hide(); 
openai_config_window.Hide()
azure_config_window.Hide()