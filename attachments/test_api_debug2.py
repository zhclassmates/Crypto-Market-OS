"""使用真实地址测试"""
import json
import sources as S

# 先从 GeckoTerminal 获取真实地址
print("1. 从 GeckoTerminal 获取地址...")
rows = S.gt_universe(1)
if rows:
    test_addr = rows[0]['address']
    print(f"   使用地址: {test_addr} ({rows[0]['symbol']})\n")

    # 测试 DexScreener
    print("2. 测试 DexScreener...")
    url = f"https://api.dexscreener.com/tokens/v1/robinhood/{test_addr}"
    res = S.get_json("dexscreener", url)
    print(f"   响应类型: {type(res)}")
    print(f"   响应长度: {len(res) if res else 0}")
    if res:
        print(f"   响应内容:\n{json.dumps(res, indent=2, ensure_ascii=False)[:3000]}")
    else:
        print("   响应为空或 None")
