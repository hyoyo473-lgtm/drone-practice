# 無人機足球 練習紀錄系統

這套系統分成三個部分：

- 網頁：`static/index.html`
- 後端：`server.py`，只用 Python 內建功能，不用安裝任何套件
- 資料庫：SQLite，是一個單一檔案 `data/drone.db`

資料存在自己的 NAS 上，再透過 Cloudflare Tunnel 接到自己的網域，例如 `drone.你的網域.com`。

```
學生手機／平板 ──https──▶ Cloudflare（你的網域） ──Tunnel──▶ NAS（Docker：網頁＋資料庫）
```

> ⚠️ **這個 repository 不包含學生資料和密碼。** `data/`（學生姓名與成績）和 `.env`（管理密碼）已經寫在 `.gitignore` 裡，不會被上傳。請把 repository 維持在 **Private（私人）**。

---

## 一、功能總覽

| 分頁 | 功能 |
|---|---|
| 📝 記錄 | 選擇學生、日期和模式。**進攻**和**防守追球**有內建的倒數計時，計數時按大按鈕 +1，時間到會發出提示音並自動填入次數。**防守守門**有內建碼錶，被進球時按「失守」，就會自動填入連續守住的秒數。成績破個人紀錄時會跳出提示。 |
| 📈 我的進步 | 三種模式各有一張折線圖，畫出「當天最佳」、「當天平均」，以及一條「班上平均」參考線。另外會列出個人最佳、平均、最近一次、進步幅度和練習量。 |
| 🏆 同學比較 | 排行榜長條圖和詳細數據表，可以選擇比較「最佳／平均／最近一次／進步幅度」。可以依位置（進攻手／防守手）和隊伍篩選，也可以把自己標示出來。下方的「進步曲線對比」把所有同學的進步曲線疊在同一張圖上。 |
| ⚙️ 管理 | 需要老師密碼。可以新增、修改、停用、刪除學生，查看和刪除紀錄，以及匯出 CSV（可以直接用 Excel 開啟）。 |

> **「換算每分鐘」是什麼？** 如果有時候限時 1 分鐘、有時候限時 2 分鐘，次數就不能直接比較。切換成「每分鐘」後，系統會把成績換算成「每分鐘成功幾次」，這樣比較才公平。

**權限設計：**學生不用登入，打開網頁就能記錄成績。修改學生名單、刪除紀錄需要老師管理密碼（`ADMIN_PIN`）。

---

## 二、運作方式

```
修改程式 → push 到 GitHub → GitHub Actions 自動檢查＋打包映像檔 → NAS 下載新映像檔
```

- 每次 push 到 `main`，GitHub 會自動檢查程式能不能正常啟動，通過後打包成映像檔 `ghcr.io/hyoyo473-lgtm/drone-practice:latest`。進度可以在 repository 的「Actions」分頁查看，大約 3～5 分鐘。
- 其他人發 Pull Request 時，只會做檢查，不會發布。檢查沒過會顯示紅色 ❌。
- **GitHub 不需要知道 NAS 的位址**，是 NAS 主動去下載映像檔。

---

## 三、第一次在 NAS 上架設

> 先確認 GitHub 的「Actions」分頁裡，第一次打包已經成功（綠色 ✅）。

### 1. 建立資料夾和兩個檔案

在 NAS 上建立 `/docker/drone-practice` 資料夾，然後在裡面放兩個檔案：

- `docker-compose.yml`：從 GitHub 上複製這個檔案的內容即可。
- `.env`：複製 `.env.example` 的內容，填入自己的管理密碼。如果 8080 跟其他網站撞到了，就把 `PORT` 改成別的數字。

NAS 上**不需要**下載整份程式碼。

### 2. 讓 NAS 可以下載映像檔

Private repository 打包出來的映像檔，預設也是私人的。用以下任一種方式讓 NAS 可以下載，**跟前一個網站的做法相同即可**：

- **方法 A：NAS 登入 GHCR**。先在 GitHub 建立一個只有 `read:packages` 權限的 Personal Access Token，然後在 NAS 的 SSH 執行：
  ```bash
  sudo docker login ghcr.io -u hyoyo473-lgtm
  ```
  密碼欄貼上 Token。
- **方法 B：把映像檔設成公開**。到 GitHub 個人頁面 →「Packages」→ drone-practice →「Package settings」→ Change visibility → Public。映像檔裡只有程式碼，沒有密碼和學生資料，但任何人都能下載。

### 3. 在 Container Manager 建立專案

打開 Container Manager →「專案」→「新增」：

- 路徑：選 `/docker/drone-practice`
- 來源：選「使用現有的 docker-compose.yml」

接著一路按下一步並建置。完成後，在校內用 `http://NAS的IP:8080` 打開網頁。上方**沒有**出現黃色的「示範模式」提示，就代表成功了。

### 4. 在原本的 Cloudflare Tunnel 新增網址

到 Cloudflare Zero Trust →「Networks」→「Tunnels」，點原本那條 Tunnel →「Public Hostname」→ 新增：

- Subdomain：`drone`
- Domain：選你的網域
- Type：`HTTP`
- URL：`NAS的Tailscale IP:8080`（`100.x.x.x`）。如果連不到，就改填 NAS 的區網 IP。

---

## 四、之後修改與更新

1. 修改程式後 push 到 GitHub（或合併其他老師的 Pull Request）。
2. 等「Actions」分頁出現綠色 ✅。
3. 在 NAS 上更新到新版。**用跟前一個網站相同的方式即可**，例如：
   - Container Manager →「專案」→ drone-practice → 停止 →「動作」→「建置」（會重新下載 latest）
   - 或在 SSH 執行：`cd /volume1/docker/drone-practice && sudo docker compose pull && sudo docker compose up -d`
   - 或用 Watchtower 自動更新

更新**不會**影響學生資料。資料庫在 NAS 的 `data/` 資料夾，不在映像檔裡。

**想在自己電腦上測試修改？** 在專案資料夾執行 `python3 server.py`，再打開 `http://localhost:8080`。這會在自己電腦上建立測試用的資料庫，不會碰到真正的學生資料。

**常改的地方：**

| 想改什麼 | 檔案 | 搜尋關鍵字 |
|---|---|---|
| 限時選項（例如加入 45 秒） | `static/index.html` | `id="recLimit"` |
| 模式的名稱與說明 | `static/index.html` | `const MODES` |
| 顏色 | `static/index.html` | `:root{` |
| 資料庫和 API | `server.py` | |

---

## 五、日常使用建議

1. **第一次使用**：老師到「管理」頁，用密碼解鎖，先把學生名單、隊伍、主要位置（進攻／防守）建好。
2. **練習時**：每位學生用手機打開網頁。記錄頁會記住上次選的學生，之後不用每次重新選。
3. **加到手機主畫面**：iPhone 用 Safari 的「分享 → 加入主畫面」，Android 用 Chrome 的「加到主畫面」。這樣用起來就像一個 App。
4. **課堂檢討**：投影「同學比較」頁。「進步幅度」能讓起點較低但很努力的學生也被看見。
5. **學生不再參加**：把學生改成「停用」就好，不要刪除。歷史資料會保留，但他不會出現在選單和排行中。

---

## 六、備份

所有資料都在 `data/drone.db` 這一個檔案裡，**GitHub 上沒有這份資料**，所以要另外備份：

- 把 `/docker/drone-practice/data` 資料夾加入 NAS 的 Hyper Backup，或任何備份排程。
- 也可以不定期到「管理」頁按「匯出 CSV」，留一份 Excel 檔。

---

## 七、常見問題

**Q：Container Manager 建置時顯示「請先建立 .env 並設定 ADMIN_PIN」？**
代表還沒有建立 `.env` 檔。請參考第三節的第 1 步。

**Q：建置時顯示 denied 或 unauthorized？**
代表 NAS 沒有權限下載映像檔。請參考第三節的第 2 步。

**Q：網頁上方一直顯示「示範模式」？**
代表網頁連不到後端。請確認你是透過 `http://NAS的IP:8080` 或你的網域打開網頁，而不是直接用瀏覽器打開 `index.html` 檔案。

**Q：圖表沒有出現？**
圖表元件（Chart.js）是從網路載入的。如果學校網路擋掉了外部網站，請下載下面這個檔案，放進 `static/` 資料夾，push 到 GitHub 後再更新 NAS。網頁會自動改用本機的檔案。

`https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js`

**Q：忘記管理密碼？**
到 NAS 上修改 `.env` 裡的 `ADMIN_PIN`，然後重新建置專案即可。資料不會遺失。
