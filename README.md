# Fundamental Chain Reaction Platform (Streamlit MVP)

這是一個可直接啟動的 Streamlit MVP，用來做：

- 公司基本面查詢
- 上下游供應鏈圖譜
- 事件衝擊模擬
- 基本面儀表板

## 功能頁面

1. 公司總覽
2. 供應鏈圖譜
3. 事件模擬器
4. 基本面儀表板

## 安裝

```bash
pip install -r requirements.txt
```

## 啟動

```bash
streamlit run app/main.py
```

## 資料結構

- `data/companies.csv`: 公司基本資料
- `data/products.csv`: 產品資料
- `data/edges.csv`: 公司 / 產品 / 市場 / 事件之間的關係
- `data/events.json`: 事件模板
- `data/financials.csv`: 基本面指標

## 關係類型

- `produces`
- `supplier_of`
- `customer_of`
- `depends_on`
- `belongs_to`
- `exposed_to`

## 後續可以擴充

- 串接 FinMind / TWSE / FRED
- Neo4j 圖資料庫
- 新聞與法說會摘要
- 自動建立事件規則
