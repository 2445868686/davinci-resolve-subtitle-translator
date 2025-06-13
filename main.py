#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取字幕 → 逐行并发 GPT 翻译 → 生成译文 SRT
"""

import os, sys, json, time, tempfile, platform, requests, concurrent.futures

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
        "WindowTitle": '字幕翻译',
        "Geometry": [700, 300, 400, 480],
        "Spacing": 10,
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
                                ui.HGroup(
                                    {"Weight": 0.1},
                                    [
                                        ui.Label({"ID": 'ModelLabel', "Text": '模型', "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                                        ui.ComboBox({"ID": 'ModelCombo', "Text": '', "Weight": 0.8}),
                                    ]
                                ),
                                ui.HGroup(
                                    {"Weight": 0.1},
                                    [
                                        ui.Label({"ID": 'TargetLangLabel', "Text": '目标语言', "Alignment": {"AlignRight": False}, "Weight": 0.2}),
                                        ui.ComboBox({"ID": 'TargetLangCombo', "Text": '', "Weight": 0.8}),
                                    ]
                                ),
                                ui.HGroup(
                                    {"Weight": 0.1},
                                    [
                                        ui.Button({"ID": 'GenerateButton', "Text": '生成'}),
                                    ]
                                ),
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
                            ]
                            
                        )
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
itm = win.GetItems()
itm["MyStack"].CurrentIndex = 0
itm["MyTabs"].AddTab("翻译")
itm["MyTabs"].AddTab("配置")
def on_my_tabs_current_changed(ev):
    itm["MyStack"].CurrentIndex = ev["Index"]
win.On.MyTabs.CurrentChanged = on_my_tabs_current_changed

def on_openai_close(ev):
    print("OpenAI API 配置完成")
    openai_config_window.Hide()
openai_config_window.On.OpenAIConfirm.Clicked = on_openai_close
openai_config_window.On.OpenAIConfigWin.Close = on_openai_close

def on_show_openai(ev):
    openai_config_window.Show()
win.On.ShowOpenAI.Clicked = on_show_openai
# ================= 用户配置 =================
OPENAI_API_KEY = "sk-wLP8n2FczZrYukonSvbozSba4HyV4cBHstEPDACv8aeI6QFH"
OPENAI_API_URL = "https://yunwu.ai/"
OPENAI_MODEL   = "gpt-4o"
TARGET_LANG    = "English"       # 目标语言
CONCURRENCY    = 6               # 并发线程数（5~10 较稳）
MAX_RETRY      = 3               # 单行最多重试次数
TIMEOUT        = 30              # 单次请求超时（秒）
# ===========================================

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
    return {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (f"You are a translation engine. Translate the user message into "
                            f"{TARGET_LANG}. Return ONLY the translated sentence.")
            },
            {"role": "user", "content": text}
        ],
        "temperature": 0
    }

def _translate_line(text):
    """翻译单行字幕，自动重试"""
    api_url = f"{OPENAI_API_URL.strip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
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

def on_close(ev):
    dispatcher.ExitLoop()
win.On.MyWin.Close = on_close


win.Show()
dispatcher.RunLoop()
win.Hide()
openai_config_window.Hide()
