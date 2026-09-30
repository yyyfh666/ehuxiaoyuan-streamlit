# -*- coding: utf-8 -*-
"""对运行中的 Streamlit 服务做真实协议级验证（不是 AppTest 模拟）。

连接 ws://127.0.0.1:8501/_stcore/stream，直接发 BackMsg(rerun_script)，
读取服务端回传的 ForwardMsg 序列，从原始字节里提取渲染文本。

运行： python live_check.py
"""

import asyncio
import re
import sys

import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg

URL = "ws://127.0.0.1:8501/_stcore/stream"


def rerun_frame() -> bytes:
    """构造 BackMsg{ rerun_script: ClientState{} }，字段号从描述符里读取，避免写死。"""
    for field in BackMsg.DESCRIPTOR.fields:
        if field.name == "rerun_script":
            tag = (field.number << 3) | 2  # wire type 2 = length-delimited
            return bytes([tag, 0x00])      # 空 ClientState
    raise RuntimeError("BackMsg 里找不到 rerun_script 字段")


def _read_varint(buf: bytes, i: int):
    shift = 0
    val = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7
    raise ValueError("varint 截断")


def walk_protobuf(buf: bytes, out: list, depth: int = 0) -> None:
    """通用 protobuf 遍历：把所有长整型字段里的可读 UTF-8 文本收集出来。"""
    if depth > 12:
        return
    i = 0
    while i < len(buf):
        try:
            key, i = _read_varint(buf, i)
        except ValueError:
            return
        field, wire = key >> 3, key & 7
        if field == 0:
            return
        try:
            if wire == 0:
                _, i = _read_varint(buf, i)
            elif wire == 1:
                i += 8
            elif wire == 2:
                ln, i = _read_varint(buf, i)
                chunk = buf[i:i + ln]
                if len(chunk) != ln:
                    return
                i += ln
                try:
                    s = chunk.decode("utf-8")
                    out.append(s)
                except UnicodeDecodeError:
                    walk_protobuf(chunk, out, depth + 1)
            elif wire == 5:
                i += 4
            else:
                return
        except Exception:
            return


def decode_text(buf: bytes) -> str:
    """从 protobuf 原始字节里提取文本：扫描出连续可解码 UTF-8 的片段。"""
    runs: list[str] = []
    i, n = 0, len(buf)
    while i < n:
        if buf[i] < 0x20 or buf[i] == 0x7F:
            i += 1
            continue
        j = i
        last_good = i
        while j < n:
            b = buf[j]
            if b < 0x80:
                width = 1
            elif 0xC2 <= b <= 0xDF:
                width = 2
            elif 0xE0 <= b <= 0xEF:
                width = 3
            elif 0xF0 <= b <= 0xF4:
                width = 4
            else:
                break
            if j + width > n:
                break
            try:
                buf[j:j + width].decode("utf-8")
            except UnicodeDecodeError:
                break
            j += width
            last_good = j
        if last_good - i >= 4:
            chunk = buf[i:last_good].decode("utf-8", errors="ignore")
            if any(c.isprintable() and not c.isspace() for c in chunk):
                runs.append(chunk)
            i = last_good
        else:
            i += 1
    return "\n".join(runs)


async def main() -> int:
    frame = rerun_frame()
    print("BackMsg 帧:", frame.hex())

    async with websockets.connect(URL, subprotocols=["streamlit"],
                                  max_size=None, open_timeout=20) as ws:
        print("WebSocket 已连接，subprotocol =", ws.subprotocol)
        await ws.send(frame)

        collected = []
        blank = 0
        for _ in range(400):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
            except asyncio.TimeoutError:
                break
            if isinstance(msg, str):
                continue
            collected.append(msg)
            text = decode_text(msg)
            if text.strip():
                blank = 0
            else:
                blank += 1
                if blank > 25:
                    break

    blob = b"\n".join(collected)
    all_text = decode_text(blob)
    print(f"收到 {len(collected)} 条 ForwardMsg，解出文本 {len(all_text)} 字符")

    checks = {
        "标题渲染（🛡️ e护校园）": "🛡️ e护校园" in all_text,
        "副标题口径声明": "只分析你主动粘贴的文本" in all_text,
        "侧边栏演示话术按钮": "快递理赔（含屏幕共享）" in all_text,
        "研判方式选择器": "端侧规则引擎（离线兜底）" in all_text,
        "输入框与提示语": "粘贴可疑短信" in all_text,
        "主按钮（开始研判/清空）": "🔍 开始研判" in all_text and "🧹 清空" in all_text,
        "10 类骗局速查区": "校园高发诈骗类型速查（10 类）" in all_text,
        "四步应对科普": "遇到疑似诈骗怎么办（四步）" in all_text,
        "底部免责声明": "不构成法律意见" in all_text,
        "无 Python 异常": not any(k in all_text for k in
                                ("Traceback", "SyntaxError", "AttributeError", "TypeError")),
    }
    ok = True
    for name, passed in checks.items():
        print(("  ✅ " if passed else "  ❌ ") + name)
        ok = ok and passed

    print("\n" + ("线上服务验证通过 ✅" if ok else "线上服务验证失败 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
