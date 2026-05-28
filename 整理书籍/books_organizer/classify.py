"""阶段 4.7：层级分类。

输出 3 个字段（写入 metadata 表）：
  category    一级分类（领域，必填）
  category2   二级分类（细分领域，可空）
  subjects    三级主题标签 JSON list（0-5 个，可空）

规则：
  - 每条规则属于某个 (cat1, cat2)，附带若干关键词；命中即归属
  - 多条规则可以命中同一本书 → 取第一条命中的 (cat1, cat2)，其他规则的 cat3 标签累加到 subjects
  - 若没匹配任何细分规则但有一级关键词（领域兜底）→ cat2 = "其他"
  - 完全没命中 → cat1 = "other"
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "books.db"


# === 层级规则 ===
# (cat1, cat2, [keywords...]) —— 顺序就是优先级
# cat3（subjects 标签）从命中的多条规则中收集
RULES = [
    # ───── tech ─────
    ("tech", "编程语言", [
        r"\bpython\b", r"\bjava(?!script)\b", r"\bc\+\+\b", r"\bgolang\b", r"\brust\b",
        r"\bkotlin\b", r"\bswift\b", r"\bruby\b", r"\bphp\b", r"\bscala\b", r"\bhaskell\b",
        r"程序设计|编程入门|代码大全|代码整洁|编程实战|算法导论|数据结构",
    ]),
    ("tech", "前端/Web开发", [
        r"\bvue\b", r"\breact\b", r"\bangular\b", r"\bnode\.?js\b", r"\bnext\.?js\b",
        r"\bjavascript\b|\btypescript\b", r"\bhtml5?\b|\bcss3?\b",
        r"前端|web开发|网页设计|web框架|webpack",
    ]),
    ("tech", "AI/机器学习", [
        r"机器学习|深度学习|神经网络|人工智能|大语言模型|llm|nlp|计算机视觉|cv|强化学习",
        r"\b(?:tensorflow|pytorch|keras|sklearn|scikit-learn)\b",
        r"ai\s*应用|gpt|chatgpt|transformer|attention\s*is\s*all",
    ]),
    ("tech", "数据科学", [
        r"数据挖掘|数据分析|数据科学|数据可视化",
        r"\b(?:pandas|numpy|spark|hadoop|kafka|flink)\b",
        r"r语言|stata|spss|excel.*分析|商业智能|bi",
    ]),
    ("tech", "系统/运维", [
        r"linux|unix|内核|操作系统|kubernetes|k8s|docker|devops|nginx",
        r"tcp/ip|网络协议|服务器|运维|网络管理|网络安全|渗透测试|信息安全",
    ]),
    ("tech", "数据库", [
        r"\b(?:mysql|postgresql|postgres|mongodb|redis|oracle|sqlserver|sqlite)\b",
        r"数据库系统|数据库原理|sql\s*权威",
    ]),
    ("tech", "数学/统计", [
        r"高等数学|微积分|线性代数|概率论|统计学|数理统计|离散数学|工程数学",
    ]),
    ("tech", "物理化学", [
        r"物理学|量子力学|相对论|电磁学|经典力学|物理化学|有机化学|无机化学",
    ]),
    ("tech", "工程技术", [
        r"机械工程|电气工程|土木工程|建筑工程|结构工程|材料科学|半导体|集成电路|嵌入式",
    ]),

    # ───── business ─────
    ("business", "金融投资", [
        r"金融|股票|基金|证券|期货|外汇|投资|理财|价值投资|量化|对冲",
        r"巴菲特|彼得林奇|查理芒格|索罗斯|霍华德马克斯",
        r"私募|风投|vc|ipo|资本市场",
    ]),
    ("business", "经济学", [
        r"经济学|宏观经济|微观经济|国富论|经济史|发展经济|政治经济|博弈论",
        r"凯恩斯|哈耶克|弗里德曼|科斯|曼昆|薛兆丰|林毅夫",
    ]),
    ("business", "管理领导", [
        r"管理学|项目管理|团队管理|领导力|战略管理|管理实践|执行力",
        r"\bmba\b|drucker|彼得德鲁克|稻盛和夫|韦尔奇",
    ]),
    ("business", "营销品牌", [
        r"营销|市场营销|品牌|广告|公关|定位|增长黑客|私域|流量",
        r"科特勒|奥格威|文案",
    ]),
    ("business", "创业商业", [
        r"创业|创新|商业模式|从零到一|精益创业|公司治理|股权",
        r"埃隆马斯克|乔布斯|贝索斯|稻盛|马云|任正非",
    ]),
    ("business", "会计税务", [
        r"会计|审计|税务|财务管理|财务分析|cpa|管理会计",
    ]),
    ("business", "人力资源", [
        r"人力资源|hr|招聘|薪酬|绩效|组织行为|hrbp",
    ]),
    ("business", "财报招股", [
        r"招股说明|招股书|招股意向|招股摘要|上市公告|问询函|配股说明|发审|挂牌",
        r"上市保荐|可转债|公司债|融资融券|审计报告",
        r"年报\b|半年报|季报|财务报表|定期报告",
    ]),
    ("business", "行业研报", [
        r"研究报告|行业报告|投资策略|证券研究|宏观研究|策略报告|深度报告|行业分析",
        r"\b(?:gartner|forrester|idc|麦肯锡|波士顿咨询|德勤|普华永道|安永|毕马威|埃森哲)\b",
        r"白皮书|蓝皮书|绿皮书",
    ]),
    ("business", "互联网商业", [
        r"互联网\+|产品经理|增长黑客|用户体验|ued|流量运营|saas|互联网思维|新零售|私域",
    ]),

    # ───── humanities ─────
    ("humanities", "哲学", [
        r"哲学|存在主义|尼采|康德|黑格尔|海德格尔|维特根斯坦|苏格拉底|柏拉图|亚里士多德",
        r"逻辑学|形而上学|认识论|伦理学",
    ]),
    ("humanities", "中国史", [
        r"史记|资治通鉴|中国通史|明朝那些事|宋史|清史|汉书|后汉书|三国志|二十四史",
        r"中国近代史|中国现代史|抗日战争|文革|改革开放史|考古",
    ]),
    ("humanities", "世界史", [
        r"世界史|二战|一战|罗马帝国|希腊史|欧洲史|美国史|战争史|文明史",
        r"剑桥(?:中国|世界|英国)史|全球通史|世界文明",
    ]),
    ("humanities", "心理学", [
        r"心理学|认知心理|发展心理|社会心理|精神分析|弗洛伊德|荣格|阿德勒",
        r"意识|潜意识|心理治疗|创伤|焦虑|抑郁",
    ]),
    ("humanities", "政治学", [
        r"政治学|国际关系|地缘政治|外交|民主|宪政|阶层|公民",
    ]),
    ("humanities", "社会学", [
        r"社会学|人类学|民族学|社会调查|社会结构|社会变迁|阶级|乡土",
        r"费孝通|马克思韦伯|涂尔干|布迪厄",
    ]),
    ("humanities", "宗教", [
        r"佛教|基督教|伊斯兰|道教|圣经|金刚经|大藏经|心经|宗教学",
    ]),
    ("humanities", "国学经典", [
        r"国学|论语|孟子|大学中庸|庄子|周易|易经|诗经|楚辞|尚书|老子|韩非|墨子|荀子|四书五经",
    ]),
    ("humanities", "中医", [
        r"中医|针灸|本草|伤寒论|黄帝内经|金匮要略|医案",
    ]),
    ("humanities", "语言学", [
        r"语言学|训诂|音韵|词源|修辞学",
        r"\b(?:chomsky|saussure|sapir|bloomfield)\b",
        r"说文解字|尔雅|广韵|文字学",
    ]),

    # ───── literature ─────
    ("literature", "中文小说", [
        r"金庸|古龙|王朔|莫言|余华|刘震云|苏童|王小波|阿城|阎连科|贾平凹|路遥|平凡的世界",
        r"红楼梦|三国演义|水浒|西游记|金瓶梅|聊斋",
    ]),
    ("literature", "外国小说", [
        r"村上春树|东野圭吾|马尔克斯|加西亚|福尔摩斯|阿加莎|海明威|卡夫卡|陀思妥|托尔斯泰",
        r"\b(?:novel|fiction|stories?)\b",
    ]),
    ("literature", "科幻奇幻", [
        r"科幻|奇幻|赛博朋克|三体|刘慈欣|阿西莫夫|刘宇昆|海伯利安|沙丘|魔戒|哈利波特|冰与火之歌",
    ]),
    ("literature", "推理悬疑", [
        r"推理|悬疑|侦探|刑警|惊悚|犯罪|阿加莎|柯南道尔|东野圭吾|岛田庄司|松本清张",
    ]),
    ("literature", "散文随笔", [
        r"散文|随笔|杂文|余秋雨|杨绛|沈从文|汪曾祺|林语堂",
    ]),
    ("literature", "诗词", [
        r"诗集|诗选|唐诗|宋词|元曲|现代诗|顾城|海子|北岛|徐志摩|席慕容|莎士比亚十四行",
    ]),
    ("literature", "美术设计", [
        r"美术|绘画|油画|国画|水彩|素描|插画|设计|平面设计|工业设计|ui设计|交互设计",
    ]),
    ("literature", "书法", [
        r"书法|楷书|行书|草书|隶书|篆书|颜真卿|王羲之|柳公权|欧阳询|赵孟頫|田英章",
    ]),
    ("literature", "音乐", [
        r"音乐|钢琴|吉他|乐理|和声|作曲|流行音乐|古典音乐|乐谱",
    ]),
    ("literature", "影视戏剧", [
        r"电影|戏剧|剧本|话剧|京剧|昆曲|表演|导演|斯坦尼斯拉夫斯基",
    ]),
    ("literature", "摄影", [
        r"摄影|纪实摄影|风光摄影|肖像|相机|镜头",
    ]),
    ("literature", "传记回忆录", [
        r"传记|自传|回忆录|乔布斯传|马斯克|曾国藩|某某传\b|个人成长史",
    ]),
    ("literature", "儿童文学", [
        r"\b(?:dahl|roald|dr\.?\s*seuss|carroll|罗尔德\s*达尔|c\.s\.\s*lewis)\b",
        r"皮皮鲁|鲁西西|查理与巧克力|哈利波特|绿野仙踪|爱丽丝梦游|小王子|夏洛的网|纳尼亚",
        r"儿童文学|童话|寓言|低幼读物|绘本|图画书|picture\s*book",
    ]),
    ("literature", "自媒体文章", [
        r"wechatbook|微信公众号|微信文章|公众号合集",
    ]),

    # ───── practical ─────
    ("practical", "中医养生", [
        r"养生|保健|针灸|按摩|经络|穴位|中医养生",
    ]),
    ("practical", "营养健身", [
        r"营养学|减肥|健身|瑜伽|跑步|马拉松|塑形|健美",
    ]),
    ("practical", "医学健康", [
        r"医学|内科|外科|妇科|儿科|肿瘤|心血管|糖尿病|高血压|健康管理",
    ]),
    ("practical", "心理疗愈", [
        r"自我成长|情绪管理|压力管理|正念|冥想|疗愈|拥抱不完美",
    ]),
    ("practical", "育儿教养", [
        r"育儿|早教|亲子|蒙特梭利|儿童心理|青少年|家庭教育|父母",
    ]),
    ("practical", "旅行", [
        r"旅行|旅游|游记|lonely planet|背包客|徒步|攻略",
    ]),
    ("practical", "烹饪美食", [
        r"烹饪|菜谱|食谱|烘焙|料理|美食|甜点|面包|蛋糕",
    ]),
    ("practical", "家居生活", [
        r"装修|家居|收纳|断舍离|整理术|园艺|宠物",
    ]),

    # ───── education ─────
    ("education", "英语", [
        r"英语|english|toefl|ielts|gre|gmat|sat|act|新概念|考研英语|大学英语|cet",
    ]),
    ("education", "日语", [r"日语|n[1-5]|jlpt|学日语|日本語"]),
    ("education", "其他外语", [r"韩语|法语|德语|西班牙语|俄语|意大利语|阿拉伯语|葡萄牙语|泰语"]),
    ("education", "考研", [r"考研|考研真题"]),
    ("education", "公务员", [r"公务员|公考|国考|省考|事业单位|行测|申论"]),
    ("education", "其他考试", [r"高考|中考|司法考试|法考|教师资格|教资|二建|一建|cpa考试"]),
    ("education", "教材课本", [
        r"教材|教程|课本|讲义|教案|学习指南|knowledge",
        r"\b(?:k1[0-2]|grade\s*\d+)\b",
    ]),
    ("education", "学习方法", [r"学习方法|高效学习|笔记|记忆|思维导图|费曼|刻意练习|认知科学"]),
    ("education", "K12/启蒙", [
        r"\bsocial\s*studies\b|\breading\s*\d|\bwriting\s*\d|\bgrade\s*\d|\bprimary\s*school",
        r"小学|学龄前|启蒙|看图说话|拼音|识字|幼儿园|kindergarten",
    ]),
    ("education", "学术论文", [
        r"\b(?:phd|博士|硕士)\s*(?:论文|学位论文|dissertation)\b|毕业设计|学位论文|开题报告",
        r"thesis|conference\s*paper",
    ]),

    # ───── reference ─────
    ("reference", "字典词典", [
        r"字典|词典|辞典|dictionary|百科全书|encyclopedia",
    ]),
    ("reference", "标准法规", [
        r"国家标准|gb\b|国标|行业标准|法规|条例|宪法|刑法|民法|合同法|劳动法",
    ]),
    ("reference", "手册年鉴", [
        r"年鉴|年报|手册|手册指南|handbook|manual|reference|工具书",
    ]),
]


COMPILED = [(c1, c2, re.compile("|".join(pats), re.IGNORECASE)) for c1, c2, pats in RULES]


def classify(title: str, author: str | None,
             publisher: str | None, rel_path: str | None) -> tuple[str, str | None, list[str]]:
    """规则匹配，返回 (cat1, cat2, subjects)。"""
    text = " ".join(filter(None, [title, author, publisher, rel_path or ""]))
    if not text:
        return "other", None, []

    cat1 = None
    cat2 = None
    subjects: list[str] = []

    for c1, c2, cre in COMPILED:
        if cre.search(text):
            if cat1 is None:
                cat1 = c1
                cat2 = c2
            # 标签：把命中的二级名称加进 subjects 当作三级 tag（去重）
            if c2 not in subjects:
                subjects.append(c2)
            if len(subjects) >= 5:
                break

    if cat1 is None:
        return "other", None, []
    return cat1, cat2, subjects[:5]


def run(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(metadata)")}
    if "category" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN category TEXT")
    if "category2" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN category2 TEXT")
    if "subjects" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN subjects TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_category ON metadata(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_category2 ON metadata(category2)")
    conn.commit()

    rows = conn.execute("""
        SELECT m.file_id, m.title, m.author, m.publisher, f.rel_path
        FROM metadata m JOIN files f ON m.file_id = f.id
    """).fetchall()
    print(f"classify: 处理 {len(rows)} 行")

    updates = []
    cnt_l1: dict = {}
    cnt_l2: dict = {}
    for file_id, title, author, publisher, rel_path in rows:
        c1, c2, subjs = classify(title or "", author, publisher, rel_path)
        cnt_l1[c1] = cnt_l1.get(c1, 0) + 1
        if c2:
            cnt_l2[(c1, c2)] = cnt_l2.get((c1, c2), 0) + 1
        updates.append((c1, c2, json.dumps(subjs, ensure_ascii=False), file_id))

    conn.executemany(
        "UPDATE metadata SET category = ?, category2 = ?, subjects = ? WHERE file_id = ?",
        updates,
    )
    conn.commit()
    conn.close()

    print(f"\nL1 分布:")
    for c, n in sorted(cnt_l1.items(), key=lambda x: -x[1]):
        print(f"  {c:12s} {n:5d}")
    print(f"\nL2 分布 (top 20):")
    for (c1, c2), n in sorted(cnt_l2.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c1:12s} / {c2:12s} {n:5d}")
    return {"l1": cnt_l1, "l2": cnt_l2}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()
    run(Path(args.db))
