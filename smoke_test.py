# -*- coding: utf-8 -*-
"""app.py 冒烟测试：用 Streamlit 官方 AppTest 无头跑一遍交互链路。

运行： python smoke_test.py
"""

import sys

from streamlit.testing.v1 import AppTest


def main() -> int:
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()

    assert not at.exception, f"首屏渲染异常: {at.exception}"
    assert at.title, "缺少标题"
    print("[1/4] 首屏渲染 OK ->", at.title[0].value)

    # 注入一条演示话术，点「开始研判」
    sample = (
        "您好，我是快递公司客服，您的包裹在运输中丢失了，我们双倍理赔。"
        "请下载XX会议APP并开启屏幕共享，把收到的验证码发给我。"
    )
    at.text_area[0].set_value(sample)
    at.button[0].click()  # 第一个按钮 = 开始研判
    at.run()
    assert not at.exception, f"研判流程异常: {at.exception}"
    body = "\n".join(m.value for m in at.markdown)
    assert "高危" in body, "快递理赔话术未被判为高危"
    print("[2/4] 端侧研判 OK -> 命中高危")

    # 导出按钮应出现
    assert at.button, "结果区缺少按钮/控件"
    print("[3/4] 结果区渲染 OK")

    # 对照：正规通知应当判为安全
    at.text_area[0].set_value(
        "本学期国家助学金材料请于本周五前交到学院办公室A302，由辅导员统一审核，"
        "学校不会通过电话或链接收集银行卡信息。"
    )
    at.button[0].click()
    at.run()
    assert not at.exception, f"对照样本异常: {at.exception}"
    body = "\n".join(m.value for m in at.markdown)
    assert "安全" in body, "正规通知被误报"
    print("[4/4] 误报抑制 OK -> 正常通知判为安全")

    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
