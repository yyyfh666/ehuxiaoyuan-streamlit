# -*- coding: utf-8 -*-
"""
e护校园 · 端侧反诈研判引擎
==========================

纯 Python、零依赖（只用标准库），可被三种前端复用：
  * Streamlit 预览版（app.py）
  * 微信小程序的云函数 / 本地兜底
  * 后端接口的"规则预判"层（先规则给底分，再交给大模型解释）

设计原则：
  1. 只依据"用户主动提交的文本"作判断，不需要任何通话/录音权限；
  2. 规则输出与大模型输出共用同一套字段，前端可无感切换；
  3. 命中即解释：每个信号都带"为什么危险"，便于做反诈教育。

自测：  python anti_fraud_engine.py
"""

from __future__ import annotations

import json
import re

# ----------------------------------------------------------------------------
# 知识库
# ----------------------------------------------------------------------------
# 每条规则 = 命中词 + 权重（权重越高，越接近"典型骗局的标志动作"）
SCAM_RULES = [
    {
        "type": "快递理赔诈骗",
        "patterns": [
            ("快递", 10), ("包裹", 10), ("丢件", 16), ("理赔", 14), ("双倍赔", 18),
            ("运费险", 10), ("派件", 8), ("退货运费", 8), ("客服", 6),
        ],
        "tagline": "真快递不会让你去借钱、开屏幕共享、报验证码。",
    },
    {
        "type": "刷单返利诈骗",
        "patterns": [
            ("刷单", 26), ("返利", 16), ("返佣", 14), ("垫付", 20), ("做任务", 10),
            ("任务", 8), ("佣金", 14), ("推荐码", 8), ("本金佣金", 18), ("一单", 8),
            ("日结", 10), ("兼职", 6), (r"返\d", 12),
        ],
        "tagline": "凡是要你先垫钱的'任务'，返利都是钩子，本金才是目标。",
    },
    {
        "type": "冒充熟人/老师诈骗",
        "patterns": [
            ("我是你", 18), ("王老师", 16), ("李老师", 16), ("辅导员", 12),
            ("头像", 6), ("换号", 12), ("急事", 12), ("先转", 18), ("别跟", 14),
            ("保密", 12), ("借点钱", 18), ("周转", 10), ("备注我", 14),
        ],
        "tagline": "换号、催转账、要保密——三件套齐了就是冒充。",
    },
    {
        "type": "冒充公检法诈骗",
        "patterns": [
            ("公安", 16), ("警察", 14), ("检察院", 18), ("法院", 14), ("洗钱", 22),
            ("涉案", 20), ("通缉", 20), ("安全账户", 26), ("资金清查", 24),
            ("办案", 14), ("传票", 16), ("涉密", 12),
        ],
        "tagline": "公检法办案从不用电话要钱、更不存在'安全账户'。",
    },
    {
        "type": "校园贷注销/征信诈骗",
        "patterns": [
            ("注销", 14), ("校园贷", 24), ("助学贷款", 18), ("征信", 22),
            ("影响征信", 24), ("贷款记录", 18), ("额度", 12), ("清空", 12),
            ("学生身份", 12), ("银保监", 22), ("贷", 8),
        ],
        "tagline": "征信改不了、也消不掉，能'帮你注销'的一定是骗子。",
    },
    {
        "type": "游戏交易诈骗",
        "patterns": [
            ("游戏", 10), ("账号交易", 18), ("皮肤", 12), ("装备", 12), ("代练", 16),
            ("解冻", 18), ("steam", 10), ("点券", 14), ("低价出", 14), ("担保交易", 16),
        ],
        "tagline": "私下交易 + 交'解冻费'，是游戏账号骗局的标准收尾。",
    },
    {
        "type": "演唱会/门票诈骗",
        "patterns": [
            ("门票", 16), ("演唱会", 18), ("内场", 14), ("代抢", 18), ("实名", 8),
            ("转票", 16), ("黄牛", 14), ("出票", 14), ("溢价", 10),
        ],
        "tagline": "脱离官方平台的'转票'，付款就是终点。",
    },
    {
        "type": "兼职/实习诈骗",
        "patterns": [
            ("入职", 10), ("押金", 18), ("保证金", 18), ("服装费", 16), ("体检费", 14),
            ("培训费", 16), ("介绍费", 14), ("工资日结", 12), ("打字员", 18),
        ],
        "tagline": "正规兼职永远不倒收钱，先收费的都是套。",
    },
    {
        "type": "助学金/补贴诈骗",
        "patterns": [
            ("助学金", 24), ("奖学金", 20), ("补贴", 14), ("发放", 8), ("学籍", 12),
            ("填卡号", 20), ("激活", 10), ("教育局", 18), ("贫困生", 16),
        ],
        "tagline": "资助政策由学校正式通知，不会电话催你报卡号。",
    },
    {
        "type": "杀猪盘/网络交友诈骗",
        "patterns": [
            ("网恋", 18), ("对象", 8), ("理财", 14), ("带你", 12), ("稳赚", 24),
            ("内幕", 20), ("平台收益", 18), ("充值提现", 22), ("导师", 14),
        ],
        "tagline": "网上认识的人带你'稳赚'，赚的是你的本金。",
    },
]

# (信号名, 正则, 权重, 解释)
SIGNAL_RULES = [
    ("要求转账/垫付/充值",
     r"(转账|汇款|垫付|充值|打款|交钱|付一下|先付|付款|扫码付|转我|先转|转\d|借点钱|借钱|凑一下|凑点|打进|转到)",
     20, "任何以'先付钱'为前提的沟通，都是资金直接外流的入口。"),
    ("索要验证码", r"(验证码|动态码|短信码|校验码|发给我|报一下.{0,4}码)",
     26, "验证码等于账户钥匙，给出验证码≈把银行卡交出去。"),
    ("要求屏幕共享/远程控制",
     r"(屏幕共享|共享屏幕|远程控制|远程协助|teamviewer|向日葵|会议app|腾讯会议|xx会议)",
     24, "屏幕共享会让你手机上的验证码、余额、密码全部暴露。"),
    ("要求下载陌生 APP", r"(下载|安装|扫码下载).{0,12}(app|应用|软件)",
     16, "脱离官方应用市场的 APP 常用于窃取信息或远程控制。"),
    ("制造紧急感/限时",
     r"(马上|立刻|立即|赶紧|尽快|两个小时|今天内|过期|逾期|限时|最后|不然|否则|即将|剩\d|名额有限)",
     12, "制造时间压力，是为了让你来不及与同学、老师、家人核实。"),
    ("要求保密/不要告诉别人",
     r"(别跟|不要跟|不能告诉|保密|别说出去|别告诉|自己知道就行)",
     14, "正规机构绝不会要求你对身边人保密——这正是骗局怕被核实的表现。"),
    ("'安全账户'/资金清查",
     r"(安全账户|安全账号|资金清查|监管账户|配合调查|洗清嫌疑)",
     28, "所谓'安全账户'是诈骗专属名词，公检法不存在这种账户。"),
    ("以征信/涉案相威胁",
     r"(影响征信|征信花|征信|黑名单|涉案|犯罪|拘留|起诉|法律责任|通缉|否则.{0,6}(将|会)|后果自负)",
     22, "用法律或征信后果制造恐惧，逼你按对方指令操作。"),
    ("冒充官方身份",
     r"(公安|警察|检察院|法院|银保监|客服中心|官方|银行工作人员|教育局|快递公司)",
     14, "身份可伪造，务必挂断后通过官方渠道自行回拨核实。"),
    ("异常链接/短链",
     r"(https?://|bit\.ly|t\.cn|dwz\.|短链|点击链接)",
     12, "短链会隐藏真实域名，点开可能进入仿冒登录页。"),
    ("通话中引导资金操作",
     r"(打开.?银行|输入密码|支付密码|转账界面|扫码支付|开通免密)",
     22, "要你边通话边操作资金账户，是同一骗局的最后一步。"),
]

# "可信上下文"证据：出现这些表述说明文本更像正规通知，而非骗局话术。
# 它的作用是抑制误报——正规通知里也会出现"助学金""辅导员"这类词。
SAFE_CONTEXT_RULES = [
    (r"(请|由|到|至).{0,8}(学院|学校|教务处|学生处|办公室|辅导员).{0,10}(办理|领取|提交|审核|交|签字|确认)",
     12, "指明了线下正规办理渠道"),
    (r"(不会|不需要|无需|不必).{0,10}(提供|索要|收集|点击|转账|汇款|缴纳)",
     18, "主动声明不会索要资金或信息"),
    (r"(官网|官方渠道|学校通知|辅导员通知|群公告|教务处通知)",
     10, "指向可自行核实的官方来源"),
    (r"(本周|下周|周一|周二|周三|周四|周五|月底|开学后).{0,10}(前|之前|截止|提交|交)",
     6, "有明确的工作流程时间点，而非催你立刻转账"),
]

# 命中这些"硬信号"时，一律不适用可信上下文抑制
HARD_SIGNAL_NAMES = {
    "要求转账/垫付/充值",
    "索要验证码",
    "要求屏幕共享/远程控制",
    "'安全账户'/资金清查",
    "通话中引导资金操作",
}

SAFE_HINTS = [
    "学校正式通知（教务处/学院官网/辅导员群内实名发布）",
    "快递官方 APP 内自助理赔、可自行回拨的官方客服",
    "96110 预警劝阻来电（这是真警察，请接听）",
]

LEVELS = ("安全", "低危", "中危", "高危")


# ----------------------------------------------------------------------------
# 核心研判
# ----------------------------------------------------------------------------
def analyze_local(text: str) -> dict:
    """纯规则研判，返回与大模型完全一致的结构化字段。"""
    raw = (text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    lowered = compact.lower()

    signals: list[dict] = []
    score = 0.0

    for name, pattern, weight, why in SIGNAL_RULES:
        if re.search(pattern, compact, flags=re.IGNORECASE):
            signals.append({"name": name, "weight": weight, "why": why})
            score += weight

    type_scores: list[tuple[str, int]] = []
    matched_kw: dict[str, list[str]] = {}
    for rule in SCAM_RULES:
        hit = []
        for kw, w in rule["patterns"]:
            try:
                m = re.search(kw, compact, flags=re.IGNORECASE)
            except re.error:
                m = kw.lower() in lowered
            if m:
                hit.append((m.group(0) if hasattr(m, "group") else kw, w))
        if hit:
            type_scores.append((rule["type"], sum(w for _, w in hit)))
            matched_kw[rule["type"]] = [kw for kw, _ in hit]

    type_scores.sort(key=lambda x: x[1], reverse=True)

    # 可信上下文证据（抑制误报）
    safe_evidence = [
        why for pattern, _w, why in SAFE_CONTEXT_RULES
        if re.search(pattern, compact, flags=re.IGNORECASE)
    ]
    has_hard_signal = any(s["name"] in HARD_SIGNAL_NAMES for s in signals)

    if type_scores:
        scam_type, top_score = type_scores[0]
    else:
        scam_type = "未匹配到典型类型"

    # 评分模型（0-100）：
    #   风险动作信号（转账、验证码、屏幕共享…）与话术类型匹配各占一半权重。
    #   单一弱关键词（只出现"助学金""兼职"）不足以抬高分数，避免误报。
    signal_score = sum(s["weight"] for s in signals)
    dialect_score = 0.0
    if type_scores:
        dialect_score += min(type_scores[0][1], 45) * 0.8
        if len(type_scores) > 1:
            dialect_score += min(type_scores[1][1], 30) * 0.15

    # 归一化到 0-100：
    #   raw  = 0.9 × 风险动作信号分 + 0.45 × 话术类型匹配分
    #   score = 100 × (raw/100)^0.7
    #   含义：① "正在被引导做的事"（转账、报验证码、开屏幕共享）权重最高；
    #        ② 再做一次 0.7 次幂拉伸，让"多个信号叠加"的文本迅速逼近高危，
    #           而只有弱关键词、没有任何资金动作的文本仍然停留在安全/低危。
    raw = 0.9 * min(signal_score, 100) + 0.45 * min(dialect_score, 100)
    if safe_evidence and not has_hard_signal:
        raw -= min(len(safe_evidence) * 16, 38)
    raw = max(0.0, min(100.0, raw))

    score = int(round(100.0 * (raw / 100.0) ** 0.7)) if raw > 0 else 0

    if score >= 60:
        level = "高危"
    elif score >= 40:
        level = "中危"
    elif score >= 18:
        level = "低危"
    else:
        level = "安全"

    # 可信上下文 + 无硬信号 → 最多停在低危
    if safe_evidence and not has_hard_signal and level in ("高危", "中危"):
        level = "低危"
        score = min(score, 40)

    confidence = 0.9 if score >= 75 else 0.78 if score >= 50 else 0.6 if score >= 22 else 0.5

    ordered = sorted(signals, key=lambda x: -x["weight"])
    top_signals = [s["name"] for s in ordered[:5]]

    if level == "安全":
        explanation = (
            "这段文本里没有出现转账、验证码、屏幕共享、陌生链接等典型资金外流动作，"
            "暂未匹配到校园高发诈骗类型。"
        )
        if safe_evidence:
            explanation += "文本还出现了正规办理渠道的表述（%s），进一步降低了可疑度。" % "、".join(safe_evidence)
        explanation += (
            "不过文本研判只能看文字，如果对方催你线下操作或转到别的平台继续聊，请立刻停手核实。"
        )
    else:
        parts = ["文本同时出现了 %d 个高危特征" % len(signals)]
        if top_signals:
            parts.append("、".join(top_signals[:3]))
        if type_scores:
            parts.append("话术结构与「%s」高度吻合" % scam_type)
        if safe_evidence:
            parts.append("但其中也包含正规流程表述（%s），风险等级已相应下调" % "、".join(safe_evidence))
        explanation = (
            "，".join(parts)
            + "。对方正在用一套完整的'取得信任 → 制造紧迫 → 引导转账'流程推进，"
            "风险和金额都会随时间放大。"
        )

    advice: list[str] = []
    if "索要验证码" in top_signals:
        advice.append("任何验证码都不要念、不要截图、不要转发给任何人")
    if "要求屏幕共享/远程控制" in top_signals:
        advice.append("立即结束屏幕共享，退出会议 APP")
    if level in ("高危", "中危"):
        advice.append("立即挂断，不要转账、不要充值、不要垫付")
        advice.append("保存聊天记录、通话记录、对方账号与链接截图")
        advice.append("拨打 96110 或到就近派出所咨询，也可先联系辅导员/班主任")
    elif level == "低危":
        advice.append("暂不操作资金：不转账、不充值、不点链接")
        advice.append("自行通过官方渠道回拨核实（不要用对方给的号码）")
        advice.append("拿不准就把截图发给辅导员或同学一起看一眼")
    else:
        advice.append("暂不需要处理，保持正常核实即可")
        advice.append("若对方后续提出转账、验证码、屏幕共享等要求，请立即停止沟通")

    if type_scores:
        rule = next(r for r in SCAM_RULES if r["type"] == scam_type)
        tip = rule["tagline"]
    else:
        tip = "凡是「先转账、后办事」的，先放一放，问一句就穿帮。"

    return {
        "risk_level": level,
        "risk_score": score,
        "is_suspected_fraud": level in ("高危", "中危"),
        "scam_type": scam_type,
        "key_signals": top_signals or ["未识别到明确高危特征"],
        "signal_detail": [{"name": s["name"], "why": s["why"]} for s in ordered],
        "matched_keywords": matched_kw.get(scam_type, []),
        "safe_evidence": safe_evidence,
        "explanation": explanation,
        "action_advice": advice,
        "educational_tip": tip,
        "confidence": round(confidence, 2),
        "engine": "端侧规则引擎（离线）",
    }


def fallback_advice_for(level: str) -> list[str]:
    if level in ("高危", "中危"):
        return ["立即挂断，不要转账", "保存聊天与通话证据", "拨打 96110 并告知辅导员"]
    return ["暂不操作资金", "通过官方渠道自行核实"]


# ----------------------------------------------------------------------------
# 自测
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    samples = {
        "快递理赔": "我是快递客服，您的包裹丢了，双倍理赔，请下载XX会议APP开屏幕共享，把验证码发我",
        "刷单返利": "亲帮忙刷个单，一单返15元，先垫付98元，本金佣金一起返",
        "冒充老师": "小李我是王老师，新号，急事先转2000给我，别跟其他同学说",
        "公检法": "这里是公安局，你涉嫌洗钱，需资金清查，把钱转入安全账户，不得告知任何人",
        "校园贷": "你在校期间注册的校园贷账户要注销，否则影响征信，请配合清空额度",
        "游戏交易": "低价出游戏账号，走担保交易，账号被冻结需要交解冻费",
        "门票诈骗": "演唱会内场门票代抢，实名转让，先付溢价定金。",
        "正常通知": "本学期国家助学金材料请于本周五前交到学院办公室A302，由辅导员统一审核，"
                    "学校不会通过电话或链接收集银行卡信息。",
        "正常闲聊": "今天下午三点图书馆三楼开会，记得带笔记本",
    }
    print("%-10s %-4s %4s  %-16s %s" % ("场景", "等级", "分值", "疑似类型", "命中信号"))
    print("-" * 96)
    for name, text in samples.items():
        r = analyze_local(text)
        print("%-10s %-4s %4d  %-16s %s" % (
            name, r["risk_level"], r["risk_score"], r["scam_type"],
            " / ".join(r["key_signals"][:3]),
        ))
    print()
    print("—— 结构化输出示例（公检法）——")
    print(json.dumps(analyze_local(samples["公检法"]), ensure_ascii=False, indent=2))
