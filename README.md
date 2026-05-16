# InkyPi Mini Weather 外掛

Mini Weather 是一個輕量化的 InkyPi 天氣外掛，重點放在電子紙螢幕上的清楚顯示、快速載入與容易設定。

Mini Weather **不是**原版 Weather 外掛的完整替代品，而是較簡化的選擇。它適合需要快速查看天氣、希望畫面更乾淨，或希望在電子紙上保持高可讀性的使用情境。

## 安裝

使用 InkyPi CLI 安裝外掛，並提供外掛 ID 與 GitHub repository URL：

```bash
inkypi plugin install mini_weather https://github.com/saulob/InkyPi-Mini-Weather
```

此外掛是 [InkyPi](https://github.com/fatihak/InkyPi) 電子紙顯示框架的擴充功能。

## 功能

- 顯示目前天氣、天氣圖示與溫度
- 顯示未來數日每日天氣預報
- 顯示每日最高溫與最低溫
- 支援多語系與在地化日期格式
- 可用座標手動指定地點
- 可用 Quick Location 快速選擇預設城市
- 依據地點處理時區，也可改用本機時區
- 可設定預報天數
- 可選擇溫度單位
- 支援 Open-Meteo 與 OpenWeatherMap 天氣來源
- 可選擇使用地點名稱或自訂文字作為標題
- 可顯示或隱藏天氣圖示
- 可選擇彩色圖示

## 新增功能與城市

Quick Location 已新增台灣常用城市，設定時可直接從下拉選單選擇，不必手動輸入經緯度：

- Taipei
- Taoyuan
- Taichung
- Tainan
- Kaohsiung

這些城市同時加入後端的地點名稱對照。當反向地理編碼失敗時，外掛仍可用 Quick Location 的城市名稱作為標題 fallback。

## 與原版 Weather 外掛的差異

- 版面更輕量、簡潔
- 重視遠距離可讀性
- Quick Location 可加快設定與測試
- 內建語系支援與在地化日期格式
- 設定項目較少，使用流程更直接
- 使用較大的文字與間距，提升電子紙畫面的辨識度

## 設定項目

- 語言選擇，並依語系顯示日期格式
- Quick Location 預設城市，或手動輸入緯度與經度
- 天氣來源：Open-Meteo 或 OpenWeatherMap
- OpenWeatherMap API key
- 溫度單位選擇
- 預報天數選擇
- 標題模式：使用地點名稱或自訂文字
- 顯示或隱藏天氣圖示
- 是否使用彩色圖示
- 時區選擇：使用地點時區或本機時區
- 樣式設定，可調整版面顯示

## 介面

- 極簡且易讀的畫面配置
- 針對小尺寸螢幕調整間距
- 清楚分隔目前天氣與未來預報
- 設計上避免電子紙顯示時產生過多殘影

## 注意事項

- Open-Meteo 不需要 API key
- OpenWeatherMap 需要 API key
- 外掛設計目標是簡單、快速，避免過重的渲染流程
- 可搭配不同螢幕尺寸與方向使用

## 截圖

- Mini Weather 在主畫面上的顯示效果
- 外掛設定畫面

<p align="center"> <img src="screenshots/example.png?v=2" width="45%" /> <img src="screenshots/settings.png?v=2" width="45%" /> </p>
