# 台股 ETF 與 USD/TWD 官方資料

主畫面的「擷取官方資料」可取得 0050、00981A 及 USD/TWD，或載入已保存的 `manifest.json` 離線重播。這兩檔 ETF 是明確限定的比較範例，沒有給予投資排序或買賣建議。

## 資料來源與可用範圍

| 資料 | 官方來源 | 此版本處理 |
| --- | --- | --- |
| ETF 日收盤 | [證交所歷史交易資訊](https://www.twse.com.tw/zh/trading/historical/stock-day.html)，`exchangeReport/STOCK_DAY` | 保留未調整收盤價與缺值，不稱為 total return |
| 收益分配 | [證交所 ETF 收益分配](https://www.twse.com.tw/zh/products/securities/etf/products/div.html)，`/rwd/zh/ETF/etfDiv` | 除息日、基準日、支付日與每單位金額；所得分類保持 unknown |
| 分割／反分割 | [證交所參考價格](https://www.twse.com.tw/zh/announcement/split/twtcau.html)，`/rwd/zh/split/TWTCAU` | 保留事件與參考價，不從四捨五入後的價格推算精確倍數 |
| USD/TWD | [中央銀行開放資料集](https://data.gov.tw/dataset/7232)，`https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day` | 一單位 USD 折合 TWD 的銀行間收盤價；非券商可成交報價 |

商品名稱及管理類別的官方參考：[0050](https://www.twse.com.tw/zh/ETFortune/etfInfo/0050)、[00981A](https://www.twse.com.tw/zh/ETFortune/etfInfo/00981A)。商品 metadata 在每次快照中凍結，離線重播不使用之後修改的名稱或分類。

## 使用方式

1. 執行 `python app/main.py --multi-asset`。
2. 點「擷取官方資料」，選取起迄日、範例代號與 TWD／USD 報告幣別。日期最多跨 24 個月；預設是最近約 90 天。
3. 完成後會切換到「官方原始資料」。表格包含來源、報價、分配日期與可得狀態；圖為未調整價格／現貨匯率相對第一筆有效值的比值，沒有配息再投入。
4. 按「執行比較」會呼叫數值服務。未調整 ETF 的總報酬、投資現金流與基準績效仍為未知，附上缺少調整／完整分配歷史的原因；現貨 FX 明確不含 carry 與槓桿。
5. 下次可由「載入研究資料」選取快照 `manifest.json`，不用再次連網。設定變更與計算失敗不會讓已載入的原始事實消失。

手動擷取：

```text
python scripts/collect_taiwan_official_data.py --symbols 0050,00981A --start 2026-09-01 --end 2026-11-19 --output-dir artifacts/taiwan-official-live
```

驗證並離線重播官方樣本（沒有市場網路請求）：

```text
python scripts/collect_taiwan_official_data.py --replay tests/fixtures/taiwan_official/capture/manifest.json
```

對經過驗證的快照產生研究報告：

```text
python scripts/run_multi_asset_research.py --official-capture --input tests/fixtures/taiwan_official/capture/manifest.json --output artifacts/official-research-report.json --engine-repo ../invest_backtest
```

報告必須存到凍結快照目錄以外，避免覆寫原始證據。

## 來源與時間完整性

每次擷取建立新的 `runs/<capture_id>/`，包含 content-addressed `raw/*.bin`、`manifest.json` 及 `request.json`。manifest 記錄完整 URL、來源身分、HTTP 狀態、實際取得完成時間、回應內容雜湊、byte 數、解析版本及範圍。HTTP 429／5xx、重試與部分回應亦留下 attempt 記錄；不成功的擷取不改動 `latest-good.json`。

這些歷史端點沒有提供逐筆原始發布時間。系統明列 `OBSERVED_AT_ACQUISITION_NOT_ORIGINAL_PUBLICATION`，以本次取得時間作為保守可得界線。此快照能重現「本次下載時取得的歷史資料」，**無法證明這些 vintage 在過去交易當時已經可得**。不會依經濟日期、檔案修改時間或交易收盤時刻倒填發布時間。

離線重播核對所有原始內容及 request 雜湊、來源 URL／順序、路徑範圍、資料日期與截止時間，並保留原來的取得時間。格式變更、錯誤代號／月份、衝突資料、非法日期或非有限數字會停止處理。缺值不補零、不 forward fill；提供日期的聯集並不代表獨立驗證過的完整交易日曆。

## 版本與仍需補齊的資料

新增 1.1.0 request/result schema，支援 `unadjusted_price`。所有 1.0.0 schema 與舊範例保持原樣。數值服務明確封鎖未調整價格的總報酬／投資現金衍生值，即使輸入誤將 coverage 旗標設為 true 也不能繞過。

目前可核對真實價格、已公告分配與匯率；以下不能由這些公開端點自動補出：

- 完整、同單位且經驗證的分割／公司行動調整與總報酬基準。
- 實際每次分配的所得分類、還本比例與完整性宣告；分配政策文字不等於該次所得組成。
- 歷史持股、底層幣別／避險、因子曝險、費用率生效紀錄與歷史發布 vintage。
- 使用者稅籍、帳戶、券商費率及清算稅務規則。預扣稅與所有交易費率預設 null；初始資金 1 僅為名目報告單位，不代表使用者帳戶資產。

本次凍結官方驗證窗為 2026/09/01–2026/11/19：53 個提供日期、兩檔 ETF 加現貨 FX 共 159 筆報價觀察、53 筆 FX、1 筆該窗相關已公告分配，10 份來源回應。這是真實快照；測試中刻意移除一筆值的畫面會標為缺值測試。

## 驗證

```text
python -m unittest discover -s tests -p "test_multi_asset*.py" -v
python contract_tests/validate_contracts.py
python scripts/taiwan_official_ui_smoke.py
python scripts/taiwan_official_ui_smoke.py --live-engine
```

第一個 UI smoke 使用已驗證的官方 frozen result，不需要私有引擎；第二個透過同層 `invest_backtest` 重新計算，不抓取市場資料。公開 CI 保存官方資料、調整缺口、來源及刻意缺值畫面，原 ABF 全套驗證保留。
