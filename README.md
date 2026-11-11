# InkyPi Mini Weather 外掛

Mini Weather 是 [InkyPi](https://github.com/fatihak/InkyPi) 的輕量天氣外掛。畫面只放目前天氣與短期每日預報，字級與間距偏大，方便在小尺寸電子紙上閱讀。

## 安裝

用外掛 ID 與 repository URL 安裝：

```bash
inkypi plugin install mini_weather https://github.com/saulob/InkyPi-Mini-Weather
```

中央氣象署來源在 `mini_weather/cwa_client.py`。要用 CWA，安裝進來的外掛目錄需要包含這個檔案。

## 畫面上有什麼

- 標題：地點名稱或自訂文字
- 在地化日期、完整星期，以及這次刷新的時間（例如「08:06 更新」）
- 目前溫度，以及當日最高溫、最低溫
- 有資料時才顯示體感溫度、降雨機率、天氣描述；缺資料時該列留空
- 今日圖示，以及其後 1 到 4 天的星期、圖示與高低溫

圖示可以關閉。彩色圖示關閉時，改用 `icons/outline/` 的線條 SVG。

## 天氣來源

| 來源 | 金鑰 | 地點 |
| --- | --- | --- |
| Open-Meteo | 不需要 | 經緯度，或 Quick Location |
| OpenWeatherMap | InkyPi `.env` 的 `OPEN_WEATHER_MAP_SECRET` | 經緯度，或 Quick Location |
| 中央氣象署（CWA） | InkyPi `.env` 的 `CWA_API_KEY` | 縣市與鄉鎮市區 |

Open-Meteo 與 OpenWeatherMap 可用 Quick Location、手動經緯度，或地圖點選。經緯度需在緯度 −90 到 90、經度 −180 到 180。時區可選地點時區或裝置時區。

地點標題解析失敗時，依序改用 Quick Location 的城市名、座標附近的 Quick Location 城市，最後顯示座標。

### 中央氣象署

選 CWA 之後，設定改為縣市與鄉鎮市區。名稱沿用[氣象資料開放平臺](https://opendata.cwa.gov.tw/)的鄉鎮市區清單；部分重名行政區會附上縣市，例如「臺北市中正區」。

預報讀取鄉鎮市區週預報（F-D0047，資料集編號為對應三日預報編號加 2）。12 小時（或更短）時段會依台北時間併成每日資料：

- 最高溫、最低溫取當日 MaxT / MinT
- 天氣現象優先取白天（起始小時小於 18）的 Wx
- 體感溫度依序取白天 AT、任一 AT、白天最高體感、當日最高體感、最低體感；資料沒有體感欄位時不顯示
- 降雨機率優先取白天的 12 小時降雨機率（PoP12h），沒有再取當日較高的值；`-` 或空白不顯示

CWA 的顯示時區固定為 `Asia/Taipei`。標題選地點時，顯示所選縣市加鄉鎮市區。

在[氣象資料開放平臺](https://opendata.cwa.gov.tw/)申請授權碼後，寫進 InkyPi 的 `.env`：

```bash
CWA_API_KEY=你的授權碼
```

OpenWeatherMap：

```bash
OPEN_WEATHER_MAP_SECRET=你的金鑰
```

## 設定

- 天氣來源：Open-Meteo、OpenWeatherMap、CWA
- 語言：荷蘭文、英文、法文、德文、印尼文、義大利文、葡萄牙文、西班牙文、繁體中文
- 溫度單位：°F、°C、K
- 預報天數：1 到 4（今天之後的天數，預設 4）
- 標題：地點名稱或自訂文字
- 顯示圖示、彩色圖示
- 時區：地點時區或裝置時區（CWA 固定台北時間，此項會隱藏）

Quick Location：Amsterdam、Berlin、Buenos Aires、Jakarta、London、Madrid、New York、Paris、Rio de Janeiro、Rome、São Paulo、Taipei、Taoyuan、Taichung、Tainan、Kaohsiung、Tokyo。

繁體中文的日期為「4月1日」這種格式，標題星期為「星期三」，預報列為「週一」到「週日」。更新時間固定 24 小時制。其他語言的 12 / 24 小時制跟隨 InkyPi 裝置設定。

## 截圖

左圖是 800×480 的畫面：繁體中文、臺北市大安區、體感溫度、降雨機率與四日預報。右圖是選了中央氣象署之後的設定頁。

<p align="center"> <img src="screenshots/example.png?v=3" width="45%" /> <img src="screenshots/settings.png?v=3" width="45%" /> </p>
