# 台股 ETF 與 USD/TWD 官方資料

主畫面的「擷取官方資料」可取得 0050、00981A、USD/TWD、ETF 淨值與兩條獨立參考指數。也可載入已保存的 `manifest.json` 離線重播。

## 資料來源與可用範圍

| 資料 | 官方來源 | 此版本處理 |
| --- | --- | --- |
| ETF 日收盤 | [證交所歷史交易資訊](https://www.twse.com.tw/zh/trading/historical/stock-day.html)，`exchangeReport/STOCK_DAY` | 保留未調整收盤價與缺值，不稱為 total return |
| 收益分配 | [證交所 ETF 收益分配](https://www.twse.com.tw/zh/products/securities/etf/products/div.html)，`/rwd/zh/ETF/etfDiv` | 除息日、基準日、支付日與每單位金額；所得分類保持 unknown |
| 分割／反分割 | [證交所參考價格](https://www.twse.com.tw/zh/announcement/split/twtcau.html)，`/rwd/zh/split/TWTCAU` | 保留事件與參考價，不從四捨五入後的價格推算精確倍數 |
| USD/TWD | [中央銀行開放資料集](https://data.gov.tw/dataset/7232)，`https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day` | 一單位 USD 折合 TWD 的銀行間收盤價；非券商可成交報價 |
| ETF 每單位淨值（NAV） | 投信投顧公會的 [NAV CSV](https://www.sitca.org.tw/MemberK0000/F/03/nav.csv)，[證券期貨局資料集 11109](https://data.gov.tw/dataset/11109) | 以受益憑證代號配對，保留來源提供的淨值日期與原幣 |
| 臺灣50報酬指數 | 證交所 [OpenAPI TAI50I](https://openapi.twse.com.tw/v1/indicesReport/TAI50I)，[證券期貨局資料集 11670](https://data.gov.tw/dataset/11670) | `TWSE.TAI50.TR` 使用 `Taiwan50TotalReturnIndex`，價格指數欄位保存為來源資訊 |
| 發行量加權股價報酬指數 | 證交所 [OpenAPI MFI94U](https://openapi.twse.com.tw/v1/indicesReport/MFI94U)，[證券期貨局資料集 11871](https://data.gov.tw/dataset/11871) | `TWSE.TAIEX.TR` 使用 `TAIEXTotalReturnIndex` |

商品名稱及管理類別的官方參考：[0050](https://www.twse.com.tw/zh/ETFortune/etfInfo/0050)、[00981A](https://www.twse.com.tw/zh/ETFortune/etfInfo/00981A)。商品 metadata 在每次快照中凍結，離線重播不使用之後修改的名稱或分類。

淨值與兩條指數的開放資料由金融監督管理委員會證券期貨局提供，原始資料來源為投信投顧公會與臺灣證券交易所。本專案保存 2026 年擷取的版本。上述三個資料集依政府資料開放授權條款第 1 版釋出，可依條款利用。 [授權條款與顯名聲明](https://data.gov.tw/license)

## 使用方式

1. 執行 `python app/main.py --multi-asset`。
2. 點「擷取官方資料」，選取起迄日、範例代號與 TWD／USD 報告幣別。日期最多跨 24 個月，預設是最近約 90 天。「一併擷取 ETF 淨值與報酬指數」預設勾選。
3. 完成後會切換到「官方原始資料」。表格包含來源、報價、分配日期與可得狀態；圖為未調整價格／現貨匯率相對第一筆有效值的比值，沒有配息再投入。
4. 第九個分頁「淨值與基準」顯示淨值、同日收盤折溢價、參考指數供應起迄日與可用日期數。載入舊快照時，該分頁顯示缺少這兩類資料的說明。
5. 按「執行比較」由數值服務計算兩條參考指數的報酬。未調整 ETF 的總報酬、投資現金流與相對基準績效保持未知，並附上資料限制。現貨 FX 明確不含 carry 與槓桿。
6. 下次可由「載入研究資料」選取快照 `manifest.json`，不用再次連網。設定變更與計算失敗時，已載入的來源資料仍可查閱。

命令列預設擷取原有 ETF 與匯率資料。加入 `--include-etf-context` 才會取得淨值與報酬指數：

```text
python scripts/collect_taiwan_official_data.py --symbols 0050,00981A --start 2026-11-02 --end 2026-11-20 --include-etf-context --output-dir artifacts/taiwan-official-live
```

驗證並離線重播新舊官方樣本：

```text
python scripts/collect_taiwan_official_data.py --replay tests/fixtures/taiwan_etf_context/capture/manifest.json
python scripts/collect_taiwan_official_data.py --replay tests/fixtures/taiwan_official/capture/manifest.json
```

對經過驗證的快照產生研究報告：

```text
python scripts/run_multi_asset_research.py --official-capture --input tests/fixtures/taiwan_etf_context/capture/manifest.json --output artifacts/official-research-report.json --engine-repo ../invest_backtest
```

報告必須存到凍結快照目錄以外，避免覆寫原始證據。

## 折溢價與指數報酬的解讀

折溢價以「同日同原幣收盤價 ÷ 每單位淨值 − 1」計算，兩者都須在研究期間內且於截止時間可得。這是收盤估值比率，無法作為成交報價。缺少同日收盤價或淨值時，折溢價維持未知。

兩條指數以 TWD 為來源幣別，供獨立研究比較。基金契約基準須另行查證，程式保留 ETF 的 `benchmark_id` 為空值。USD 報告按中央銀行同日 USD/TWD 收盤匯率換算兩端指數水準，再計算報酬。這是本程式的換算結果，指數供應商的官方 USD 版本可能採用不同匯率慣例。臺灣50系列的原幣與除息報酬定義見基本規則第 1.6–1.7 節。 [FTSE TWSE 基本規則](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-twse-taiwan-index-series-ground-rules.pdf) · [臺灣指數公司 TAIEX 指數資料](https://backend.taiwanindex.com.tw/api/downloadFile/IndexFiles/218/tw) · [TAIEX 報酬指數](https://taiwanindex.com.tw/indexes/IR0001)

## 來源與時間完整性

每次擷取建立新的 `runs/<capture_id>/`，包含 content-addressed `raw/*.bin`、`manifest.json` 及 `request.json`。manifest 記錄完整 URL、來源身分、HTTP 狀態、實際取得完成時間、回應內容雜湊、byte 數、解析版本及範圍。HTTP 429／5xx、重試與部分回應亦留下 attempt 記錄；不成功的擷取不改動 `latest-good.json`。

這些歷史端點沒有提供逐筆原始發布時間。系統明列 `OBSERVED_AT_ACQUISITION_NOT_ORIGINAL_PUBLICATION`，以本次取得時間作為保守可得界線。此快照能重現「本次下載時取得的歷史資料」，**無法證明這些 vintage 在過去交易當時已經可得**。不會依經濟日期、檔案修改時間或交易收盤時刻倒填發布時間。

離線重播核對所有原始內容及 request 雜湊、來源 URL／順序、路徑範圍、資料日期與截止時間，並保留原來的取得時間。格式變更、錯誤代號／月份、衝突資料、非法日期或非有限數字會停止處理。缺值不補零、不 forward fill；提供日期的聯集並不代表獨立驗證過的完整交易日曆。

淨值端點提供最新快照，分頁保留各基金實際提供的淨值日期。兩個指數端點沒有歷史起迄日參數，實際供應範圍以擷取的回應為準。分頁顯示來源實際供應起迄日，覆蓋率分母則是所選 ETF 提供日期的聯集。只有落在聯集內且可用的指數觀察才進入報酬比較。

## 版本與仍需補齊的資料

包含淨值與報酬指數的快照使用 manifest 1.1.0 與解析器 `taiwan-official-1.1.0`。原有 manifest 1.0.0 與解析器 `taiwan-official-1.0.1` 仍可離線重播。兩種快照都使用既有的數值 request/result schema 1.1.0。未調整 ETF 的總報酬與投資現金衍生值仍需完整、可靠的價格調整與配息資料，聲明完整性的旗標無法解除這項限制。

以下研究輸入仍須從其他資料或使用者設定取得。

- 完整、同單位且經驗證的分割／公司行動調整與各基金適用的契約基準。
- 實際每次分配的所得分類、還本比例與完整性宣告；分配政策文字不等於該次所得組成。
- 歷史持股、底層幣別／避險、因子曝險、費用率生效紀錄與歷史發布 vintage。
- 使用者稅籍、帳戶、券商費率及清算稅務規則。預扣稅與所有交易費率預設 null；初始資金 1 僅為名目報告單位，不代表使用者帳戶資產。

實際稅後收益及所得解讀須依各次分配組成與適用稅費規則判斷。明確設定單一稅率只代表指定的情境假設，無從補足來源欠缺的所得分類。

含淨值的凍結樣本於臺北時間 2026-11-21 取得，研究期間為 2026-11-02 至 2026-11-20。五項資產合計 75 筆比較觀察，其中兩條指數各提供 15 個日期，另有 15 筆匯率與 9 份原始回應。兩檔 ETF 的淨值日期均為 2026-11-20。

舊版凍結樣本的研究期間為 2026-09-01 至 2026-11-19，有 53 個提供日期。兩檔 ETF 與現貨 FX 合計 159 筆報價觀察，另有 53 筆匯率、1 筆該期間相關的已公告分配與 10 份原始回應。

## 驗證

```text
python -m unittest discover -s tests -p "test_multi_asset*.py" -v
python contract_tests/validate_contracts.py
python scripts/taiwan_official_ui_smoke.py
python scripts/taiwan_official_ui_smoke.py --live-engine
python scripts/taiwan_etf_context_ui_smoke.py
python scripts/taiwan_etf_context_ui_smoke.py --live-engine
```

介面驗證預設使用經核對的凍結結果。ETF 淨值與指數的驗證可用 `--manifest` 指定另一個含此資料的快照，並讀取同目錄的 `result.json`。指定 `--live-engine` 時，由本機 `invest_backtest` 重新計算。可用 `INVEST_BACKTEST_REPO` 指定其路徑。兩種模式的市場資料皆來自本機。公開 CI 保存官方資料、折溢價、指數比較、刻意缺值與舊快照畫面。
