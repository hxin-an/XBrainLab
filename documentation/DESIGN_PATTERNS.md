# 軟體設計模式筆記 (Design Patterns Cheatsheet)

本筆記整理了軟體工程中最常見的設計模式，適合作為日常開發與複習的參考資料。

---

## 一、創建型模式 (Creational Patterns)
**核心問題**：如何有效地創建物件？

### 1. 單例模式 (Singleton)
- **解決的問題**：某些類別（如資料庫連線池、日誌記錄器、全域設定公用物件）在整個程式生命週期中「絕對只需要一個」實例。如果不受控地建立多個實例，會導致資源浪費、資料不一致或硬體存取衝突。
- **核心思想**：由類別自己負責確保只有一個實例存在，並提供一個全域訪問點。
- **程式碼範例**：
```python
class AppConfig:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            # 初始化時載入預設值
            cls._instance.settings = {"theme": "dark", "lang": "zh-TW"}
        return cls._instance

# 證明無論呼叫幾次，拿到的都是同一個物件
config1 = AppConfig()
config2 = AppConfig()
print(config1 is config2)  # Output: True
```

### 2. 工廠模式 (Factory Pattern)
- **解決的問題**：避免代碼中充斥著大量的 `if-else` 或 `switch` 來決定要創建物件的類型。當物件的種類繁多或建立過程複雜時，直接實例化會導致主程式碼與具體類別高度耦合。
- **核心思想**：定義一個用於創建物件的介面（工廠），讓「創建物件」與「使用物件」分離。你只需要告訴工廠你要什麼，工廠會幫你處理複雜的製造細節。
- **程式碼範例**：
```python
class Logger:
    def log(self, msg): pass

class FileLogger(Logger):
    def log(self, msg): print(f"寫入檔案: {msg}")

class DBLogger(Logger):
    def log(self, msg): print(f"存入資料庫: {msg}")

class LoggerFactory:
    @staticmethod
    def get_logger(log_type: str) -> Logger:
        if log_type == "file":
            return FileLogger()
        elif log_type == "db":
            return DBLogger()
        raise ValueError("不支援的日誌類型")

# 使用者只需要知道工廠，不需要知道具體的 FileLogger 類別
logger = LoggerFactory.get_logger("file")
logger.log("一條測試訊息")
```

### 3. 建造者模式 (Builder)
- **解決的問題**：當一個物件的建構過程非常複雜（例如：一個物件有 10 個參數，且其中 8 個是選填的），傳統的建構子會導致參數列表超級長且難以閱讀（這被稱為「伸縮式建構子」問題）。
- **核心思想**：將複雜物件的「建構步驟」與「零件表示」分離。透過「一步步 (Step-by-Step)」設定參數的方式來產出物件。
- **應用場景**：複雜的配置物件、HTTP 請求封裝、自定義報告產生。
- **程式碼範例**：
```python
class Computer:
    def __init__(self):
        self.cpu = ""
        self.gpu = ""
        self.ram = ""

class ComputerBuilder:
    def __init__(self):
        self.computer = Computer()

    def add_cpu(self, cpu):
        self.computer.cpu = cpu
        return self  # 回傳 self 實現鏈接式呼叫 (Chaining)

    def add_gpu(self, gpu):
        self.computer.gpu = gpu
        return self

    def add_ram(self, ram):
        self.computer.ram = ram
        return self

    def build(self):
        return self.computer

# 使用方式清晰易讀
my_pc = (ComputerBuilder()
         .add_cpu("M3 Max")
         .add_ram("64GB")
         .add_gpu("40-core GPU")
         .build())
```

### 4. 抽象工廠模式 (Abstract Factory)
- **核心概念**：**「套裝 (Kit) / 家族 (Family)」**。如果不使用抽象工廠，你就像在 IKEA散買家具，很容易把不同風格（Windows 視窗配 Mac 按鈕）混在一起導致出錯。
- **解決的問題**：強制確保一組互相依賴的物件能「成套」地被創建，防止不相容的組件被混用。
- **比喻**：
    - **工廠模式**：你跟店員說「我要椅子」，他給你一張椅子。
    - **抽象工廠**：你跟店員說「我要北歐風客廳套裝」，他給你一整套風格統一的椅子+桌子+沙發。
- **程式碼範例**：
```python
# 抽象工廠介面：定義一套產品該有的清單
class StyleFactory:
    def create_chair(self): pass
    def create_table(self): pass

# 具體套裝 A: 現代風 (Modern)
class ModernFactory(StyleFactory):
    def create_chair(self): return ModernChair()
    def create_table(self): return ModernTable()

# 具體套裝 B: 復古風 (Retro)
class RetroFactory(StyleFactory):
    def create_chair(self): return RetroChair()
    def create_table(self): return RetroTable()

# 使用方式：呼叫端只需選擇「套裝工廠」，就保證拿到的所有產品風格一致
factory = ModernFactory()
chair = factory.create_chair()
table = factory.create_table()
```

### 5. 原型模式 (Prototype)
- **解決的問題**：
    1. 創建物件的成本很高（例如需要讀取大型磁碟檔案、進行複雜解密或資料庫查詢）。
    2. 需要產出與現有物件狀態完全一模一樣的新物件，但又不希望外部知道內部的複雜結構。
- **核心思想**：直接「複製 (Clone)」一個已經存在的實例作為基礎，而不是從零開始重新建構。
- **應用場景**：遊戲中的大量小兵怪物、具有複雜初始設定的訓練任務範本。
- **程式碼範例**：
```python
import copy

class ComplexObject:
    def __init__(self, name):
        self.name = name
        self.data = self._expensive_operation() # 假設這步要跑很久

    def _expensive_operation(self):
        # 模擬耗時操作
        return [i for i in range(1000000)]

    def clone(self):
        # 使用深拷貝來複製自己
        return copy.deepcopy(self)

# 使用方式
prototype = ComplexObject("預設範本")
new_obj = prototype.clone() # 這次複製非常快，不需要重新 run _expensive_operation
new_obj.name = "修改後的快照"
```
- **Python 提示**：Python 內建的 `copy` 模組讓這個模式非常直觀，通常不需要像 Java 那樣顯式定義介面。

---

## 二、結構型模式 (Structural Patterns)
**核心職責**：定義如何將類別與物件組合成更大、更靈活的系統結構。其重點在於簡化系統間的依賴關係，並在不改動原始碼的前提下實現功能擴充。

### 1. 門面模式 (Facade)
- **技術痛點**：底層子系統（Subsystem）組件過多且關係複雜，外部系統難以掌握繁雜的操作順序（如：初始化、執行流程、清理資源等）。
- **核心職責**：**「簡化 (Simplification)」** 與 **「封裝 (Encapsulation)」**。為一組複雜的子系統類別提供一個高層級的「統一介面」。
- **解決方案**：不只是初始化，更重要的是封裝 **「常用工作流 (Common Workflows)」**。
- **技術效益**：降低外部與內部的耦合度，實現「單一窗口化」操作，避免外部誤用子系統內部的細節。
- **程式碼範例**：
```python
class DataCleaner: def clean(self): ...
class ModelLoader: def load(self): ...
class ExecutionEngine: def run(self): ...

class PipelineFacade:
    """門面不只管初始化，更管『整個工作流』"""
    def __init__(self):
        self.cleaner = DataCleaner()
        self.loader = ModelLoader()
        self.engine = ExecutionEngine()

    def run_training_pipeline(self):
        # 將複雜的跨模組操作封裝成一個簡單方法
        self.cleaner.clean()
        self.loader.load()
        self.engine.run()
```

### 2. 適配器模式 (Adapter)
- **技術痛點**：既有類別（Legacy Class）的介面協定與當前系統要求的標準介面（Target Interface）不一致。
- **解決方案**：建立一個中間層，負責將非標準介面封裝並轉譯為目標介面。
- **技術效益**：實現在不修改原始碼的情境下整合第三方組件或遺留系統。
- **技術權衡 (Trade-off)**：
    - **效能**：適配器會引入一層額外的函式呼叫。在一般業務邏輯中損耗可忽略不計，但在高頻運算迴圈中需注意。
    - **重構 vs 適配**：若舊組件是系統核心且數據格式轉換開銷過大，應優先考慮「重構 (Refactoring)」而非適配。適配器更適合用於「邊界整合」。
- **程式碼範例**：
```python
class LegacyAPI:
    def get_old_format(self): return {"v": 1.0}

class CommonInterface:
    def get_data(self) -> dict: pass

class APIAdapter(CommonInterface):
    """介面轉譯層"""
    def __init__(self, legacy_api):
        self._api = legacy_api

    def get_data(self):
        old_data = self._api.get_old_format()
        return {"value": old_data["v"]} # 格式轉換
```

### 3. 裝飾器模式 (Decorator)
- **核心思維**：**「包裹 (Wrapping)」**。不需要修改原始類別（修改基因），而是像穿衣服一樣遞增功能。
- **技術痛點**：
    - **繼承爆炸**：若使用繼承來擴充功能，每增加一個功能組合（如：A+B, A+C, A+B+C），就需要建立一個新的子類別，導致系統極難維護。
    - **靜態限制**：繼承在編譯時期就定死了，無法在執行程式時（Runtime）動態地為某個特定物件加減功能。
- **解決方案**：定義一個裝飾器類別，它內部持有原始物件，並在外層包裹額外的行為邏輯。
- **技術效益**：實現「組合優於繼承」，能以極少數量的類別達成極其複雜的功能組合。
- **程式碼範例**：
```python
# 核心組件
class CoreWorker:
    def work(self): print("執行核心任務")

# 裝飾器 A：增加日誌功能
class LogWrapper:
    def __init__(self, worker): self._worker = worker
    def work(self):
        print("[Log] 準備開始...")
        self._worker.work()

# 裝飾器 B：增加計時功能
class TimerWrapper:
    def __init__(self, worker): self._worker = worker
    def work(self):
        start = time.time()
        self._worker.work()
        print(f"[Timer] 耗時: {time.time() - start}秒")

# 使用方式：像「套娃」一樣自由組合包裹
worker = CoreWorker()
full_worker = TimerWrapper(LogWrapper(worker)) # 同時具備日誌與計時
full_worker.work()
```

### 4. 代理模式 (Proxy)
- **技術痛點**：直接存取原始物件可能帶來性能消耗（如大物件載入）、權限風險或不必要的遠端通訊。
- **解決方案**：提供一個佔位物件（Placeholder）以控制、過濾或延遲對目標物件的存取。
- **關鍵類型**：
    - **虛擬代理 (Virtual Proxy)**：延遲初始化 (Lazy Initialization)。
    - **保護代理 (Protection Proxy)**：存取權限控管。
    - **緩存代理 (Caching Proxy)**：儲存昂貴運算結果。

### 5. 橋接模式 (Bridge)
- **技術痛點**：抽象層與實現層（Implementation）深度耦合，導致兩者難以獨立進行修改或擴展。
- **解決方案**：將抽象部分（Abstraction）與其實現部分（Implementer）分離，使兩者可以獨立變化。
- **應用場景**：跨平台圖形系統（抽象畫圖路徑 vs 具體繪圖引擎）、可更換資料庫的系統。

### 6. 組合模式 (Composite)
- **技術痛點**：系統需要以統一的方式處理個別物件（Leaf）與物件群組（Composite），如檔案系統的檔案與資料夾。
- **解決方案**：定義一個共通介面，讓單一物件與組合物件具備一致的操作性。
- **技術效益**：簡化客戶端定義，使其不需區分操作的是單一物件還是樹狀結構。

### 7. 享元模式 (Flyweight)
- **技術痛點**：當系統中存在大量相似物件時，重複的狀態（精確位置、固定屬性）會消耗巨大的記憶體資源。
- **解決方案**：透過共享技術（Shared State）有效地支援大量細粒度的物件。
- **關鍵概念**：分離「內部狀態 (Intrinsic State)」（可共享）與「外部狀態 (Extrinsic State)」（不可共享）。
- **技術效益**：顯著降低系統記憶體消耗。

---

---

## 三、行為型模式 (Behavioral Patterns)
**核心問題**：物件之間如何有效地溝通與分配職責？

### 1. 觀察者模式 (Observer / Pub-Sub)
- **用途**：定義物件間的一對多依賴關係，當一個物件狀態改變時，自動通知所有依賴者。
- **應用場景**：事件系統、UI 更新、訊息推送。
```python
class Subject:
    def __init__(self):
        self._observers = []

    def subscribe(self, observer):
        self._observers.append(observer)

    def notify(self, data):
        for obs in self._observers:
            obs.update(data)
```

### 2. 策略模式 (Strategy)
- **用途**：定義一系列算法，將每個算法封裝起來，使它們可以互換。
- **應用場景**：排序策略、支付方式選擇、驗證規則。
```python
class PaymentContext:
    def __init__(self, strategy):
        self._strategy = strategy

    def pay(self, amount):
        self._strategy.execute(amount)
```

### 3. 命令模式 (Command)
- **用途**：將請求封裝成物件，使請求可以被儲存、排隊或撤銷。
- **應用場景**：Undo/Redo 功能、任務佇列、遠端命令執行。

### 4. 狀態模式 (State)
- **用途**：允許物件在內部狀態改變時改變其行為。
- **應用場景**：訂單狀態機、遊戲角色狀態、工作流程引擎。

---

## 四、架構模式 (Architectural Patterns)
**核心問題**：如何組織整個軟體系統的分層與職責？

### 1. Controller-Service-Repository (CSR)
現代後端系統的經典分層方式（XBrainLab 目前採用的架構）：
- **Controller**：接收指令、驗證輸入、協調流程。
- **Service**：執行核心業務邏輯（如：信號處理算法）。
- **Repository/State**：數據存取與持久化（如：Study 物件）。

### 2. MVC (Model-View-Controller)
將使用者介面（View）與資料邏輯（Model）分開，透過 Controller 中轉。

---

## 五、並行模式 (Concurrency Patterns)
**核心問題**：如何處理多執行緒 (Multi-threading) 與非同步作業？

### 1. 生產者/消費者 (Producer-Consumer)
- 一方負責產出任務（如：載入檔案），一方負責處理任務（如：訓練模型）。透過「佇列 (Queue)」平衡雙方速度。

### 2. 主僕模式 (Master-Worker)
- 一個主線程負責分發任務，多個子線程（Worker）負責並行執行，最後匯總結果。

---

## 六、設計模式速查總結

| 模式 | 類型 | 一句話總結 |
| :--- | :--- | :--- |
| Singleton | 創建型 | 確保只有一個實例 |
| Factory | 創建型 | 用方法代替 `new` 來創建物件 |
| Builder | 創建型 | 分步驟建構複雜物件 |
| Facade | 結構型 | 為複雜系統提供簡單介面 |
| Adapter | 結構型 | 讓不兼容的介面可以一起工作 |
| Decorator | 結構型 | 動態添加功能，不改變原始類別 |
| Observer | 行為型 | 狀態變化時自動通知訂閱者 |
| Strategy | 行為型 | 封裝可互換的算法 |
| Command | 行為型 | 將請求封裝成物件 |
| State | 行為型 | 根據內部狀態改變行為 |

---

## 六、學習資源
- **經典書籍**：《Design Patterns: Elements of Reusable Object-Oriented Software》(Gang of Four)
- **線上資源**：[Refactoring Guru](https://refactoring.guru/design-patterns)
