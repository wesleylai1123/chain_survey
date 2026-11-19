# 跨資產與 ETF 研究

這是新增的獨立研究流程。ABF 既有資料、指標定義、驗證門檻及操作入口沒有被替換。

## 三個 repo 的現況與分工

| Repo | 本次角色 |
| --- | --- |
| chain_survey | 主產品、Asset/Instrument 契約、JSON/CSV adapter、ETF look-through、研究證據與 Tk 比較介面 |
| invest_backtest | 私有計算服務：總報酬、風險、配息現金情境、基準差異、跨資產相關/OOS/市場狀態 |
| market-temperature-dashboard | 沿用既有 MarketRegimeV1 CLI，不改動市場分數；消費來源新鮮度與可得時間 |

研究資料透過 JSON 傳遞，沒有跨 repo 的 Python import，亦未改動舊 ResearchSignalV1 / BacktestResultV1 / MarketRegimeV1。完整[資料契約](multi-asset-contract.md)可用於新增供應商 adapter。

## 啟動與使用

1. 將 `chain_survey` 與包含 multi-asset service 的 `invest_backtest` feature branch 放在同層資料夾，安裝各自依賴。也可設定 `INVEST_BACKTEST_REPO` 指向引擎，或在畫面選擇資料夾。
2. 執行 `python app/main.py --multi-asset`，或主畫面點「跨資產 / ETF 研究」。初始畫面沒有市場報價或預設投資績效。
3. 點「載入研究資料」，選擇 normalized request JSON 或 CSV bundle manifest。資料可包含股票、指數型 ETF、主動型 ETF、基準與 FX。
4. 選擇 accumulation（再投入）或 income（保留現金）、基準幣別與資料截止時間，再按「執行比較」。編輯設定會立即作廢舊結果。
5. 查看資產比較、配息與現金流、滾動報酬、相關性/OOS/市場狀態、持股/FX 曝險、指標證據，以及資料品質與假設。比率為小數（0.05 = 5%），現金以基準幣別顯示。

命令列研究報告：

```text
python scripts/run_multi_asset_research.py --input request.json --output artifacts/research-report.json --engine-repo ../invest_backtest
```

輸出是 `MultiAssetResearchReportV1`，內含未變更的 `MultiAssetResultV1`、來源 lineage 與研究 context。原始數據不被輸出覆寫。修改或刪除來源資料後，需重新計算；結果保留輸入 bytes hash。

## JSON / CSV 輸入

Canonical request schema 位於 `contracts/multi-asset/v1/schema.json`。每個價格、分配、FX 與持股快照必須明列來源 URL、snapshot_id、published_at 與 acquired_at。可得時間取兩時間的較晚者；空時間保留為不可用紀錄。不同 vintage 不混為當時已知資料。

CSV bundle manifest 格式：

```json
{
  "request": {"完整 request metadata 與其他資料集合": "依 canonical schema 填寫"},
  "files": {"observations": "prices.csv", "distributions": "distributions.csv", "fx_rates": "fx.csv"}
}
```

`request` 必須包含所有 required 欄位（可先放空 observations/distributions/fx_rates 陣列）。CSV 欄名直接對應該集合 schema；數字空格與時間空格轉成 null，不以檔案修改時間替代。JSON/CSV 的原始 SHA256 均保留；CSV 必須位於 manifest 所在目錄內。CLI 加 `--csv-bundle`。不同供應商的欄名、調整方式與單位必須由 adapter 明確轉換後才能使用。

只有明確標示 **SYNTHETIC TEST ONLY** 的合約範例與 `tests/fixtures/multi_asset` 可用於離線介面驗證；它們並非真實市場績效。畫面截圖同樣標示 TEST ONLY。**本次未宣稱已接通可靠的完整即時市場 feed。**

## 計算與限制

- 總報酬資料分成 total-return index 與 split-adjusted price + 完整同單位分配歷史。前者不能再加配息；後者缺 corporate action 或 distribution coverage 就不報總報酬。指數的股息再投資概念可參考 [MSCI 官方計算方法](https://www.msci.com/eqb/methodology/meth_docs/MSCI_Index_Calculation_Methodology_May2026.pdf)。
- 總報酬使用除息日；可支用現金使用支付日與當日精確匯率。累積情境於支付日有價格及 FX 時才再投入。無可用支付日、稅率、費用或必要匯率時，相關數值為 null 並附原因。過去 12 個月配息率不等於收益率；return of capital 分開呈現。
- Sharpe/Sortino 明列風險利率；未知利率不視為 0。接近零波動的比率為未知，避免浮點誤差製造極端績效。費用率具可得時間，僅顯示，避免對已扣費 NAV 重複扣款。
- 被動 ETF 比較同期間、同幣別基準的 tracking difference/error。主動 ETF 顯示 active return、CAPM alpha、beta、information ratio。缺基準即不可用，不臨時選擇有利基準。
- 回撤含初始資產。rolling return 僅計算連續完整視窗；缺一端價格/匯率就留缺值。跨資產相關顯示全樣本、時間順序 70/30 train/OOS 與樣本數；這是描述性研究，並非因果證明或調參後的獨立策略驗證。
- CAGR 依實際經過日數年化。月頻 grid 必須逐月連續；日頻超過 14 天的間距會拒絕計算，這只是保守防誤用門檻，並未證明交易日完整。市場狀態只標在其可得日與區間起始日相同的期間，不把舊標籤向後補滿；不足時保留未分類。
- FX 定義為「一單位 base 貨幣換 rate 單位 quote 貨幣」；只使用同日期直接或反向匯率，不偷偷補值。FX 資產為未加槓桿現貨，不含 carry、展期或利差。
- 持股未揭露權重保留 UNKNOWN。產業、因子及底層幣別揭露不足就顯示 coverage；ETF 計價幣別不能代替底層幣別，也不能推估未揭露避險或衍生品。
- ABF 公司或 ETF 底層持股可連結既有 target-relative leading/coincident/lagging catalog 與 driver/model/sensitivity 研究參考。catalog 不是觀察資料，沒有將 ETF 權重換算成 EPS beta；多空證據分開提供，共用事件不算獨立支持。
- 統一稅率是使用者情境，未套用個人居住地、帳戶別、租稅協定或清算資本利得規則。未宣稱為完整個人稅務結果。

## 驗證與 CI

```text
python -m unittest discover -s tests -v
python contract_tests/validate_contracts.py
python scripts/multi_asset_ui_smoke.py
python scripts/multi_asset_ui_smoke.py --frozen
```

公開 repo CI 驗證 schema、adapter、UI 與綁定 exact request hash 的合成 frozen result；私有引擎 CI 使用固定 commit 的公開產品與 regime producer，執行真實 subprocess integration 並重算 golden 指標，不需要新增跨私有 repo 憑證。`MULTI_ASSET_REQUIRE_PEERS=1` 使缺 peer 成為錯誤，避免整合檢查被靜默跳過。原 ABF 全套 CI 保留。

## 後續資料源缺口

1. 有授權且可稽核的股價、NAV、split/corporate-action 與退市歷史；資料需能重現歷史 vintage。
2. 追蹤基準的 gross/net total-return series、計價幣別與費用生效歷史。
3. ETF 發行商除息/支付日、分配來源（收益/資本利得/還本）、更正版本及完整覆蓋宣告。
4. 持股/產業/因子/幣別與避險部位的發布時間；不透明 ETF 只能提供部分曝險。
5. 同日期與支付日的可靠 FX、交易日曆及必要 carry/forward 資料。
6. 使用者指定的稅籍、帳戶、券商費率與適用法規資料。未取得前，稅後結果仍只是明列假設的情境。
