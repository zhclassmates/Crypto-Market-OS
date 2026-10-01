"""测试 API 调用"""
import sources as S
import config as C

print("1. 测试 DexScreener API...")
try:
    # 测试一个示例地址
    test_addr = "0x4ed4e862860bed51a9570b96d89af5e1b0efefed"
    result = S.ds_tokens([test_addr])
    print(f"   DexScreener OK: got {len(result)} tokens")
    if result:
        for addr, data in result.items():
            print(f"   Token: {addr[:10]}... {data.get('symbol')} liq=${data.get('liq')}")
except Exception as e:
    print(f"   DexScreener ERROR: {e}")

print("\n2. 测试 GeckoTerminal Universe...")
try:
    rows = S.gt_universe(1)  # 只获取1页测试
    print(f"   GeckoTerminal OK: got {len(rows)} tokens")
    if rows:
        print(f"   First token: {rows[0]}")
except Exception as e:
    print(f"   GeckoTerminal ERROR: {e}")

print("\n3. 测试 Blockscout...")
try:
    test_addr = "0x4ed4e862860bed51a9570b96d89af5e1b0efefed"
    result = S.bs_token(test_addr)
    print(f"   Blockscout OK: {result}")
except Exception as e:
    print(f"   Blockscout ERROR: {e}")

print("\n完成！")
