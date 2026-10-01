"""系統內建模板（海外短影音常見題材）。API 啟動時同步到 templates 表（tenant_id 為空）。

修改這裡的內容後重新部署即可更新；使用者要調整請在後台「複製為自訂模板」。
每個鏡頭：brief 給 AI 和拍攝人員看的重點、scene 期望畫面（asset_analyzer.SCENES）、seconds 建議秒數。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Template

STRATEGIES = {
    "persona": "人設型（建立信任）",
    "traffic": "流量型（吸引觀看）",
    "conversion": "成交型（促成詢價）",
}


def _shot(brief: str, scene: str, seconds: int) -> dict:
    return {"brief": brief, "scene": scene, "seconds": seconds}


BUILTIN_TEMPLATES: list[dict] = [
    {
        "key": "factory_tour",
        "name": "Factory Tour 工廠巡禮",
        "strategy": "persona",
        "description": "帶觀眾快速走一圈工廠，展現規模與專業，適合當帳號的第一支影片。",
        "shots": [
            _shot("開場鉤子：一句話點出「這裡每天生產多少 / 供應哪些國家」，引起好奇", "workshop", 3),
            _shot("車間全景，介紹工廠規模與主力產品", "workshop", 5),
            _shot("生產線運作中的畫面，說明關鍵製程或設備", "production", 5),
            _shot("品質檢驗環節，強調把關標準", "production", 4),
            _shot("成品或倉庫畫面，展示產能與庫存", "warehouse", 4),
            _shot("結尾：邀請詢價或追蹤，帶出聯絡方式", "team", 3),
        ],
    },
    {
        "key": "how_its_made",
        "name": "How It's Made 製作過程",
        "strategy": "traffic",
        "description": "從原料到成品的完整過程，流程感強、完播率高。",
        "shots": [
            _shot("開場鉤子：展示最終成品，問「你知道它是怎麼做出來的嗎？」", "product_closeup", 3),
            _shot("原料或半成品登場", "production", 4),
            _shot("第一道關鍵工序", "production", 4),
            _shot("第二道關鍵工序（最有看點的動作）", "production", 4),
            _shot("組裝或收尾處理", "production", 4),
            _shot("成品特寫，點出品質與用途，結尾行動呼籲", "product_closeup", 4),
        ],
    },
    {
        "key": "product_closeup",
        "name": "Product Close-up 產品特寫",
        "strategy": "conversion",
        "description": "近距離展示產品細節與賣點，適合主打單一產品。",
        "shots": [
            _shot("開場鉤子：用產品最大的賣點或痛點開場", "product_closeup", 3),
            _shot("材質與做工細節特寫", "product_closeup", 4),
            _shot("關鍵功能或規格展示", "product_closeup", 4),
            _shot("使用情境或尺寸對比", "product_closeup", 4),
            _shot("結尾：可客製、起訂量或交期，邀請詢價", "product_closeup", 3),
        ],
    },
    {
        "key": "quality_check",
        "name": "Quality Check 品質檢驗",
        "strategy": "conversion",
        "description": "展示檢驗流程與標準，降低海外買家的不信任感。",
        "shots": [
            _shot("開場鉤子：「出貨前每一件都要經過這幾關」", "production", 3),
            _shot("外觀檢查或尺寸量測", "production", 4),
            _shot("功能或耐用度測試", "production", 5),
            _shot("不合格品挑出、說明標準", "production", 4),
            _shot("合格品包裝，結尾強調品質承諾與詢價", "packing", 4),
        ],
    },
    {
        "key": "order_packing",
        "name": "Order Packing 訂單出貨",
        "strategy": "traffic",
        "description": "打包出貨的療癒畫面，順便展示出貨量與包裝規格。",
        "shots": [
            _shot("開場鉤子：「這批貨要送到哪個國家？」", "packing", 3),
            _shot("產品逐一裝箱", "packing", 5),
            _shot("包材、防護細節", "packing", 4),
            _shot("封箱、貼標、堆棧板", "packing", 4),
            _shot("裝車或倉庫全景，結尾邀請下單", "warehouse", 4),
        ],
    },
    {
        "key": "satisfying_process",
        "name": "Satisfying Process 療癒製程",
        "strategy": "traffic",
        "description": "挑最有節奏感、最療癒的機台或手工畫面，衝流量用。",
        "shots": [
            _shot("最療癒的一個動作直接開場，不說廢話", "production", 3),
            _shot("同一製程的另一個角度", "production", 4),
            _shot("另一個有節奏感的工序", "production", 4),
            _shot("成品一排排完成的畫面", "production", 4),
            _shot("結尾一句話介紹工廠，邀請追蹤", "workshop", 3),
        ],
    },
    {
        "key": "behind_the_scenes",
        "name": "Behind the Scenes 幕後花絮",
        "strategy": "persona",
        "description": "輕鬆展示工廠日常與人情味，拉近和觀眾的距離。",
        "shots": [
            _shot("開場鉤子：「你沒看過的工廠日常」", "workshop", 3),
            _shot("員工工作中的自然畫面", "team", 4),
            _shot("有趣或意想不到的小細節", "workshop", 4),
            _shot("團隊互動或休息時間", "team", 4),
            _shot("結尾：一句溫暖的話，邀請追蹤", "team", 3),
        ],
    },
    {
        "key": "meet_the_team",
        "name": "Meet the Team 認識團隊",
        "strategy": "persona",
        "description": "介紹老闆、工程師、業務等關鍵人物，建立「真人在做事」的信任感。",
        "shots": [
            _shot("開場鉤子：人物面對鏡頭打招呼", "talking_head", 3),
            _shot("介紹此人負責的工作與年資", "team", 5),
            _shot("他工作中的畫面", "production", 4),
            _shot("他對品質或客戶的一句承諾", "talking_head", 4),
            _shot("結尾：歡迎聯絡，提供服務", "team", 3),
        ],
    },
    {
        "key": "day_in_the_life",
        "name": "Day in the Life 一天的工作",
        "strategy": "persona",
        "description": "以時間軸呈現工廠一天，故事感強。",
        "shots": [
            _shot("清晨開工：「早上 7 點，工廠的一天開始了」", "outdoor", 3),
            _shot("上午：生產線啟動", "production", 4),
            _shot("中午：品檢或團隊用餐", "team", 4),
            _shot("下午：包裝出貨", "packing", 4),
            _shot("傍晚收工，結尾邀請追蹤", "workshop", 3),
        ],
    },
    {
        "key": "buyer_tips",
        "name": "Buyer Tips 採購避坑",
        "strategy": "traffic",
        "description": "用專業知識教海外買家怎麼挑供應商、避免踩雷，建立專家形象。",
        "shots": [
            _shot("開場鉤子：「採購這類產品，90% 的人都犯過這個錯」", "talking_head", 3),
            _shot("錯誤一：常見的低品質陷阱，用畫面對比", "product_closeup", 5),
            _shot("錯誤二：規格或材質的差異", "product_closeup", 5),
            _shot("我們的做法，展示製程或檢驗", "production", 4),
            _shot("結尾：有問題歡迎留言或私訊", "talking_head", 3),
        ],
    },
    {
        "key": "customization",
        "name": "Customization 客製化選項",
        "strategy": "conversion",
        "description": "展示可客製的顏色、尺寸、Logo、包裝，直接引導詢價。",
        "shots": [
            _shot("開場鉤子：「你的品牌也可以有自己的款式」", "product_closeup", 3),
            _shot("顏色、材質選項", "product_closeup", 4),
            _shot("Logo 印刷或客製工序", "production", 4),
            _shot("客製包裝", "packing", 4),
            _shot("結尾：起訂量與打樣時間，邀請詢價", "product_closeup", 4),
        ],
    },
    {
        "key": "raw_to_finished",
        "name": "Raw to Finished 原料到成品",
        "strategy": "traffic",
        "description": "強烈的前後對比：一堆原料變成精緻成品。",
        "shots": [
            _shot("開場：原料畫面，「這堆東西會變成什麼？」", "production", 3),
            _shot("加工中的轉變過程", "production", 5),
            _shot("快完成的關鍵一步", "production", 4),
            _shot("揭曉成品特寫", "product_closeup", 4),
            _shot("結尾：說明用途與可訂購", "product_closeup", 3),
        ],
    },
    {
        "key": "store_walkthrough",
        "name": "Store Walkthrough 門店導覽",
        "strategy": "persona",
        "description": "實體門店用：帶觀眾逛一圈，介紹環境、商品與服務。",
        "shots": [
            _shot("開場：門口或招牌，「歡迎來到我們的店」", "storefront", 3),
            _shot("店內環境全景", "storefront", 4),
            _shot("主打商品陳列", "product_closeup", 4),
            _shot("服務或店員互動", "team", 4),
            _shot("結尾：地址、營業時間或線上下單方式", "storefront", 3),
        ],
    },
    {
        "key": "why_choose_us",
        "name": "Why Choose Us 為什麼選我們",
        "strategy": "conversion",
        "description": "條列三個核心優勢，適合放在主頁置頂。",
        "shots": [
            _shot("開場鉤子：「找供應商之前，先看這三點」", "workshop", 3),
            _shot("優勢一（例如產能 / 交期），配對應畫面", "production", 5),
            _shot("優勢二（例如品質 / 認證），配對應畫面", "production", 5),
            _shot("優勢三（例如客製 / 服務），配對應畫面", "team", 5),
            _shot("結尾：明確的行動呼籲", "talking_head", 3),
        ],
    },
]


def sync_builtin_templates(db: Session) -> None:
    """把程式內的內建模板同步到資料庫；已移除的內建模板會停用（保留紀錄，避免文案失去來源）。"""
    existing = {t.builtin_key: t for t in db.scalars(select(Template).where(Template.builtin_key.is_not(None)))}
    keys = set()
    for item in BUILTIN_TEMPLATES:
        keys.add(item["key"])
        template = existing.get(item["key"]) or Template(builtin_key=item["key"], tenant_id=None)
        template.name = item["name"]
        template.strategy = item["strategy"]
        template.description = item["description"]
        template.shots = item["shots"]
        template.is_active = True
        db.add(template)
    for key, template in existing.items():
        if key not in keys:
            template.is_active = False
    db.commit()
