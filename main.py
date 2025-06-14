#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取字幕 → 逐行并发 GPT 翻译 → 生成译文 SRT
"""
# ================= 用户配置 =================
SCRIPT_NAME = "DaVinci TTS "
SCRIPT_VERSION = "3.3"
SCRIPT_AUTHOR = "HEIBA"
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
WINDOW_WIDTH = 400 
WINDOW_HEIGHT = 500
X_CENTER = (SCREEN_WIDTH - WINDOW_WIDTH) // 2
Y_CENTER = (SCREEN_HEIGHT - WINDOW_HEIGHT) // 2
SCRIPT_KOFI_URL="https://ko-fi.com/heiba"
SCRIPT_WX_URL = "https://mp.weixin.qq.com/s?__biz=MzUzMTk2MDU5Nw==&mid=2247484626&idx=1&sn=e5eef7e48fbfbf37f208ed9a26c5475a&chksm=fabbc2a8cdcc4bbefcb7f6c72a3754335c25ec9c3e408553ec81c009531732e82cbab923276c#rd"
OPENAI_API_KEY = "sk-wLP8n2FczZrYukonSvbozSba4HyV4cBHstEPDACv8aeI6QFH"
OPENAI_API_URL = "https://yunwu.ai/"
CONCURRENCY    = 10               # 并发线程数（5~10 较稳）
MAX_RETRY      = 3               # 单行最多重试次数
TIMEOUT        = 30              # 单次请求超时（秒）
# ===========================================

import os, sys, json, time, tempfile, platform, requests, concurrent.futures
from functools import partial
# 1. 获取脚本所在目录（备用）
script_path = os.path.dirname(os.path.abspath(sys.argv[0]))
config_dir = os.path.join(script_path, 'config')
settings_file = os.path.join(config_dir, 'translator_settings.json')


try:
    import DaVinciResolveScript as dvr_script
    from python_get_resolve import GetResolve
    print("DaVinciResolveScript from Python")
except ImportError:
    
    if platform.system() == "Darwin": 
        resolve_script_path1 = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Examples"
        resolve_script_path2 = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    elif platform.system() == "Windows": 
        resolve_script_path1 = os.path.join(os.environ['PROGRAMDATA'], "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Examples")
        resolve_script_path2 = os.path.join(os.environ['PROGRAMDATA'], "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Modules")
    else:
        raise EnvironmentError("Unsupported operating system")

    sys.path.append(resolve_script_path1)
    sys.path.append(resolve_script_path2)

    try:
        import DaVinciResolveScript as dvr_script
        from python_get_resolve import GetResolve
        print("DaVinciResolveScript from DaVinci")
    except ImportError as e:
        raise ImportError("Unable to import DaVinciResolveScript or python_get_resolve after adding paths") from e
    
# 获取Resolve实例
resolve = GetResolve()
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

win = dispatcher.AddWindow(
    {
        "ID": 'MyWin',
        "WindowTitle": SCRIPT_NAME+SCRIPT_VERSION, 
        "Geometry": [X_CENTER, Y_CENTER, WINDOW_WIDTH, WINDOW_HEIGHT],
        "Spacing": 10,
        "StyleSheet": """
        * {
            font-size: 14px; /* 全局字体大小 */
        }
        """
    },
    [
        ui.VGroup(
            [
                ui.TabBar({"Weight": 0.0, "ID": "MyTabs"}),
                ui.Stack(
                    {"Weight": 1.0, "ID": "MyStack"},
                    [
                        ui.VGroup(
                            {"Weight": 1},
                            [
                                ui.TextEdit({"ID": "SubTxt", "Text": "", "ReadOnly": False, "Font": ui.Font({"PixelSize": 14}),"Weight": 1}),
                                ui.Label({"ID": 'TrackLabel', "Text": '翻译轨道', "Alignment": {"AlignRight": False}, "Weight": 0.1}),
                                ui.ComboBox({"ID": 'TrackCombo', "Text": '', "Weight": 0.1}),
                                ui.Label({"ID": 'OpenAIModelLabel', "Text": '模型', "Alignment": {"AlignRight": False}, "Weight": 0.1}),
                                ui.ComboBox({"ID": 'OpenAIModelCombo', "Text": '', "Weight": 0.1}),
                                ui.Label({"ID": 'TargetLangLabel', "Text": '目标语言', "Alignment": {"AlignRight": False}, "Weight": 0.1}),
                                ui.ComboBox({"ID": 'TargetLangCombo', "Text": '', "Weight": 0.1}),
                                ui.Button({"ID": 'TransButton', "Text": '翻译',"Weight": 0.1}),
                                
                            ]
                            

                        ),
                        ui.VGroup(
                            {"Weight": 1},
                            [
                                ui.HGroup({"Weight": 0.1}, [
                                ui.Label({"Text": "OpenAI API", "Alignment": {"AlignLeft": True}, "Weight": 0.1}),
                                ui.Button({"ID": "ShowOpenAI", "Text": "配置","Weight": 0.1}),
                                
                                ]
                                ),
                                ui.HGroup({"Weight": 0.1}, [
                                ui.CheckBox({"ID": "LangEnCheckBox", "Text": "EN", "Checked": True, "Alignment": {"AlignRight": True}, "Weight": 0}),
                                ui.CheckBox({"ID": "LangCnCheckBox", "Text": "简体中文", "Checked": False, "Alignment": {"AlignRight": True}, "Weight": 1}),
                                
                                ]),
                                ui.TextEdit({"ID": "infoTxt", "Text": "", "ReadOnly": True, "Font": ui.Font({"PixelSize": 14}),"Weight": 1})
                            ]
                            
                        ),
                        
                    ]

                )

            ]
        )
            
    
    ]
)

# openai配置窗口
openai_config_window = dispatcher.AddWindow(
    {
        "ID": "OpenAIConfigWin",
        "WindowTitle": "OpenAI API",
        "Geometry": [900, 400, 400, 200],
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
                ui.HGroup({"Weight": 1}, [
                    ui.Label({"ID": "OpenAIBaseURLLabel", "Text": "Base URL", "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                    ui.LineEdit({"ID": "OpenAIBaseURL", "Text":"","PlaceholderText": "https://api.openai.com/v1", "Weight": 0.8}),
                ]),
                ui.HGroup({"Weight": 1}, [
                    ui.Label({"ID": "OpenAIApiKeyLabel", "Text": "密钥", "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                    ui.LineEdit({"ID": "OpenAIApiKey", "Text": "", "EchoMode": "Password", "Weight": 0.8}),
                    
                ]),
                ui.HGroup({"Weight": 1}, [
                    ui.Button({"ID": "OpenAIConfirm", "Text": "确定","Weight": 1}),
                    ui.Button({"ID": "OpenAIRegisterButton", "Text": "注册","Weight": 1}),
                ]),
                
            ]
        )
    ]
)

translations = {
    "cn": {
        "Tabs": ["翻译","配置"],
        "OpenAIModelLabel":"模型：",
        "TrackLabel":"翻译轨道：",
        "TargetLangLabel":"目标语音：",
        "TransButton":"开始翻译",
        "ShowOpenAI": "配置",
        "OpenAILabel":"填写OpenAI API信息",
        "OpenAIBaseURLLabel":"Base URL",
        "OpenAIApiKeyLabel":"密钥",
        "OpenAIConfirm":"确定",
        "OpenAIRegisterButton":"注册",
        
    },

    "en": {
        "Tabs": ["Translator", "Configuration"],
        "OpenAIModelLabel":"Model:",
        "TrackLabel":"Translate Track:",
        "TargetLangLabel":"Target Language:",
        "TransButton":"Translate",
        "ShowOpenAI": "Config",
        "OpenAILabel":"OpenAI API",
        "OpenAIBaseURLLabel":"Base URL",
        "OpenAIApiKeyLabel":"Key",
        "OpenAIConfirm":"OK",
        "OpenAIRegisterButton":"Register",
        
    }
}    

items = win.GetItems()
openai_items = openai_config_window.GetItems()
items["MyStack"].CurrentIndex = 0

for tab_name in translations["cn"]["Tabs"]:
    items["MyTabs"].AddTab(tab_name)
    
def on_my_tabs_current_changed(ev):
    items["MyStack"].CurrentIndex = ev["Index"]
win.On.MyTabs.CurrentChanged = on_my_tabs_current_changed

track_counts  = ["1","2","3","4","5"]
for track in track_counts:
    items["TrackCombo"].AddItem(track)

openai_models = ["gpt-4o-mini","gpt-4o-mini","gpt-4.1-nano","gpt-4.1",]
for model in openai_models:
    items["OpenAIModelCombo"].AddItem(model)

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
    "OPENAI_API_KEY": "",
    "OPENAI_BASE_URL": "",
    "OPENAI_MODEL": 0,
    "TARGET_LANG":0,
    "CN":True,
    "EN":False,
}

check_or_create_file(settings_file)
saved_settings = load_settings(settings_file) 

def close_and_save(settings_file):
    settings = {

        "CN":items["LangCnCheckBox"].Checked,
        "EN":items["LangEnCheckBox"].Checked,
        
        "OPENAI_API_KEY": openai_items["OpenAIApiKey"].Text,
        "OPENAI_BASE_URL": openai_items["OpenAIBaseURL"].Text,
        "OPENAI_MODEL": items["OpenAIModelCombo"].CurrentIndex,
        "TARGET_LANG":items["TargetLangCombo"].CurrentIndex,


        
    }

    save_settings(settings, settings_file)

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
    items["OpenAIModelCombo"].CurrentIndex = saved_settings.get("OPENAI_MODEL", default_settings["OPENAI_MODEL"])
    items["TargetLangCombo"].CurrentIndex = saved_settings.get("TARGET_LANG", default_settings["TARGET_LANG"])
    items["LangCnCheckBox"].Checked = saved_settings.get("CN", default_settings["CN"])
    items["LangEnCheckBox"].Checked = saved_settings.get("EN", default_settings["EN"])
    openai_items["OpenAIApiKey"].Text = saved_settings.get("OPENAI_API_KEY", default_settings["OPENAI_API_KEY"])
    openai_items["OpenAIBaseURL"].Text = saved_settings.get("OPENAI_BASE_URL", default_settings["OPENAI_BASE_URL"])    

if items["LangEnCheckBox"].Checked :
    switch_language("en")
else:
    switch_language("cn")

def on_openai_close(ev):
    print("OpenAI API 配置完成")
    openai_config_window.Hide()
openai_config_window.On.OpenAIConfirm.Clicked = on_openai_close
openai_config_window.On.OpenAIConfigWin.Close = on_openai_close

def on_show_openai(ev):
    openai_config_window.Show()
win.On.ShowOpenAI.Clicked = on_show_openai

# -------- DaVinci Resolve 相关工具函数 --------
def connect_resolve():
    resolve = dvr_script.scriptapp("Resolve")
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    timeline = project.GetCurrentTimeline()
    fps = float(project.GetSetting("timelineFrameRate"))
    return resolve, project, timeline, fps

def get_subtitles(timeline):
    subtitles = []
    track_count = timeline.GetTrackCount("subtitle")
    for track_idx in range(1, track_count + 1):
        if not timeline.GetIsTrackEnabled("subtitle", track_idx):
            continue
        for item in timeline.GetItemListInTrack("subtitle", track_idx):
            subtitles.append({
                "start": item.GetStart(),
                "end"  : item.GetEnd(),
                "text" : item.GetName()
            })
    return subtitles

def frame_to_timecode(frame, fps):
    total_seconds = frame / fps
    hours = int(total_seconds // 3600)
    minutes = int(total_seconds % 3600 // 60)
    seconds = int(total_seconds % 60)
    msec    = int((total_seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{msec:03}"

def write_srt(subs, fps):
    fd, srt_path = tempfile.mkstemp(suffix=".srt", prefix="translated_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for idx, sub in enumerate(subs, 1):
            f.write(f"{idx}\n"
                    f"{frame_to_timecode(sub['start'], fps)} --> {frame_to_timecode(sub['end'], fps)}\n"
                    f"{sub['text']}\n\n")
    return srt_path

# -------------------------------------------

# -------------- GPT 调用逻辑 ----------------
def _build_payload(text):
    """构造单行翻译请求 payload"""
    model = items["OpenAIModelCombo"].CurrentText
    target_lang = items["TargetLangCombo"].CurrentIndex
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (f"You are a translation engine. Translate the user message into "
                            f"{target_lang}. Return ONLY the translated sentence.")
            },
            {"role": "user", "content": text}
        ],
        "temperature": 0
    }

def _translate_line(text):
    """翻译单行字幕，自动重试"""
    api_key  = openai_items["OpenAIApiKey"].Text
    api_url = f"{openai_items["OpenAIBaseURL"].Text.strip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type" : "application/json"
    }
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = requests.post(api_url,
                                 headers=headers,
                                 data=json.dumps(_build_payload(text)),
                                 timeout=TIMEOUT)
            # 429/503 也会 raise_for_status
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == MAX_RETRY:
                # 最后一次仍失败，直接抛给上层；也可返回原文并记录
                raise RuntimeError(f"字幕翻译失败：{text[:20]}...") from e
            time.sleep(2 ** attempt)  # 指数退避

def translate_parallel(text_list):
    """并发翻译字幕列表，返回相同长度的译文列表"""
    results = [None] * len(text_list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        future_to_idx = {pool.submit(_translate_line, txt): idx
                         for idx, txt in enumerate(text_list)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
    return results
# -------------------------------------------

# ------------------- 主流程 -----------------
def main():
    resolve, project, timeline, fps = connect_resolve()
    subs = get_subtitles(timeline)
    if not subs:
        print("❌ 没有找到字幕块"); return

    # 1. 抽取原文
    ori_texts = [s["text"] for s in subs]

    # 2. 并发翻译
    print(f"开始并发翻译，共 {len(ori_texts)} 行，线程数 {CONCURRENCY} …")
    trans_texts = translate_parallel(ori_texts)

    # 3. 写回字幕对象
    for sub, new_txt in zip(subs, trans_texts):
        sub["text"] = new_txt

    # 4. 生成 SRT
    srt_path = write_srt(subs, fps)
    print("✅ 翻译完成！SRT 文件路径：", srt_path)

    #5. （可选）导入时间线
    media_pool = project.GetMediaPool()
    mp_items   = media_pool.ImportMedia([srt_path])
    if mp_items:
         timeline.AppendToTimeline(mp_items)
         print("✅ 已把字幕添加到时间线")
    else:
         print("❌ SRT 导入失败")
    
def on_trans_button_clicked(ev):
    
    resolve, project, timeline, fps = connect_resolve()
    subs = get_subtitles(timeline)
    if not subs:
        print("❌ 没有找到字幕块"); return
    
    all_text = ""

    for index, subtitle in enumerate(subs):
        start_time = frame_to_timecode(subtitle['start'], fps)
        end_time = frame_to_timecode(subtitle['end'], fps)
        all_text += (
        f"{index + 1}\n"
        f"{start_time} --> {end_time}\n"
        f"{subtitle['text']}\n\n"
    )
    
    items["SubTxt"].Text = all_text

    # 1. 抽取原文
    ori_texts = [s["text"] for s in subs]

    # 2. 并发翻译
    print(f"开始并发翻译，共 {len(ori_texts)} 行，线程数 {CONCURRENCY} …")
    trans_texts = translate_parallel(ori_texts)

    # 3. 写回字幕对象
    for sub, new_txt in zip(subs, trans_texts):
        sub["text"] = new_txt

    # 4. 生成 SRT
    srt_path = write_srt(subs, fps)
    print("✅ 翻译完成！SRT 文件路径：", srt_path)

win.On.TransButton.Clicked = on_trans_button_clicked

def on_close(ev):
    close_and_save(settings_file)
    dispatcher.ExitLoop()
win.On.MyWin.Close = on_close


win.Show()
dispatcher.RunLoop()
win.Hide()
openai_config_window.Hide()
