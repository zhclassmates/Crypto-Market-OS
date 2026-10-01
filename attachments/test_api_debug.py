"""调试 DexScreener API 响应"""
import json
import sources as S

test_addr = "0x4ed4e862860bed51a9570b96d89af5e1b0efefed"
print(f"测试地址: {test_addr}\n")

# 直接调用 get_json
url = f"https://api.dexscreener.com/tokens/v1/robinhood/{test_addr}"
print(f"URL: {url}\n")

res = S.get_json("dexscreener", url)
print(f"响应类型: {type(res)}")
print(f"响应内容:\n{json.dumps(res, indent=2, ensure_ascii=False)[:2000]}")
