"""
core/lexicon.py
----------------
Centralized lexical expansion dictionary.

Use this for:
- search normalization
- backend service search expansion
- RAG retrieval query expansion
- mapping model-selected search terms to canonical service groups

Do NOT use this as a giant intent router.
The LLM should still understand user intent and choose tools.
"""

FIXAGO_SYNONYMS = {
    "điện": [
        # Vietnamese / no-accent
        "điện", "dien", "sửa điện", "sua dien", "thợ điện", "tho dien",
        "chập điện", "chap dien", "chập", "chap", "chập cháy", "chap chay",
        "ổ cắm", "o cam", "ổ điện", "o dien", "công tắc", "cong tac",
        "bóng đèn", "bong den", "đèn", "den", "đèn led", "den led",
        "đèn tuýp", "den tuyp", "đèn chùm", "den chum",
        "tủ điện", "tu dien", "cầu dao", "cau dao", "aptomat", "atomat",
        "cb", "nhảy cb", "nhay cb", "rớt cb", "rot cb", "sập cb", "sap cb",
        "cầu chì", "cau chi", "dây điện", "day dien", "đứt dây", "dut day",
        "điện âm tường", "dien am tuong", "điện nổi", "dien noi",
        "rò điện", "ro dien", "giật điện", "giat dien", "giật tê", "giat te",
        "mất điện", "mat dien", "sụp nguồn", "sup nguon",
        "xẹt lửa", "xet lua", "tia lửa", "tia lua", "tóe lửa", "toe lua",
        "mùi khét", "mui khet", "khét điện", "khet dien",
        "chập chờn", "chap chon", "chớp nháy", "chop nhay",
        "quạt trần", "quat tran", "quạt hút", "quat hut",
        "công tơ", "cong to", "đồng hồ điện", "dong ho dien",

        # English
        "electric", "electrical", "electrician", "electrical repair",
        "power issue", "power outage", "no power", "power failure",
        "short circuit", "electrical short", "burnt outlet", "burned outlet",
        "socket", "outlet", "plug socket", "wall socket",
        "switch", "light switch", "lamp", "light", "led light",
        "breaker", "circuit breaker", "breaker trips", "tripped breaker",
        "fuse", "fuse box", "electrical panel", "power panel",
        "wiring", "wire", "broken wire", "loose wire",
        "electric shock", "sparks", "spark", "burning smell",
        "ceiling fan", "exhaust fan",

        # Russian
        "электрика", "электрик", "ремонт электрики", "электричество",
        "нет света", "нет электричества", "пропало электричество",
        "короткое замыкание", "замыкание", "искрит", "искра", "искры",
        "розетка", "выключатель", "лампа", "светильник", "проводка",
        "провод", "щиток", "электрощит", "автомат", "автомат выбивает",
        "выбивает автомат", "предохранитель", "запах гари", "горит проводка",
        "удар током", "бьет током", "мигает свет", "вентилятор",

        # Hindi / Hinglish
        "bijli", "electric ka kaam", "electrician", "bijli repair",
        "light nahi hai", "power nahi hai", "current nahi aa raha",
        "short circuit", "spark", "sparking", "socket jal gaya",
        "switch kharab", "fan kharab", "light kharab", "wire toot gaya",
        "wiring problem", "breaker trip", "mcb trip", "fuse ud gaya",
        "current lag raha", "jalne ki smell", "burning smell",
        "बिजली", "इलेक्ट्रिक", "इलेक्ट्रीशियन", "करंट", "शॉर्ट सर्किट",
        "चिंगारी", "स्विच", "सॉकेट", "तार", "लाइट", "पंखा", "फ्यूज",

        # French
        "électricité", "electricite", "électricien", "electricien",
        "réparation électrique", "reparation electrique",
        "panne électrique", "panne electrique", "pas de courant",
        "court-circuit", "prise électrique", "prise electrique",
        "interrupteur", "lumière", "lumiere", "ampoule",
        "disjoncteur", "tableau électrique", "tableau electrique",
        "fusible", "câblage", "cablage", "fil électrique", "fil electrique",
        "étincelle", "etincelle", "odeur de brûlé", "odeur de brule",
        "ventilateur de plafond",
    ],

    "nước": [
        # Vietnamese / no-accent
        "nước", "nuoc", "sửa nước", "sua nuoc", "thợ nước", "tho nuoc",
        "ống nước", "ong nuoc", "đường ống", "duong ong",
        "rò nước", "ro nuoc", "rỉ nước", "ri nuoc", "rò rỉ", "ro ri",
        "rỉ rỉ", "ri ri", "nhỏ giọt", "nho giot",
        "bể ống", "be ong", "bục ống", "buc ong", "vỡ ống", "vo ong",
        "tắc cống", "tac cong", "nghẹt cống", "nghet cong",
        "nghẹt", "nghet", "tắc", "tac", "thông tắc", "thong tac",
        "bồn cầu", "bon cau", "lavabo", "chậu rửa", "chau rua",
        "vòi nước", "voi nuoc", "vòi sen", "voi sen", "vòi xịt", "voi xit",
        "xi phông", "xi phong", "ống xả", "ong xa",
        "phễu thu sàn", "pheu thu san", "thoát sàn", "thoat san",
        "van nước", "van nuoc", "phao cơ", "phao co", "phao điện", "phao dien",
        "máy bơm", "may bom", "máy bơm nước", "may bom nuoc",
        "bồn nước", "bon nuoc", "bồn inox", "bon inox",
        "máy nước nóng", "may nuoc nong", "bình nóng lạnh", "binh nong lanh",
        "nước yếu", "nuoc yeu", "mất nước", "mat nuoc",
        "nước đục", "nuoc duc", "hôi cống", "hoi cong", "bốc mùi", "boc mui",
        "trào ngược", "trao nguoc",

        # English
        "plumbing", "plumber", "water repair", "pipe", "water pipe",
        "leaking pipe", "pipe leak", "water leak", "leak", "leakage",
        "dripping", "dripping water", "broken pipe", "burst pipe",
        "clogged drain", "blocked drain", "drain blockage",
        "clogged toilet", "blocked toilet", "toilet clogged",
        "sink", "wash basin", "lavatory", "lavabo",
        "faucet", "tap", "shower", "shower head",
        "floor drain", "drain pipe", "waste pipe",
        "water valve", "water pump", "pump not working",
        "water tank", "hot water heater", "water heater",
        "weak water pressure", "low water pressure", "no water",
        "dirty water", "bad smell", "sewer smell", "backflow",

        # Russian
        "сантехника", "сантехник", "ремонт сантехники", "вода",
        "труба", "водопровод", "течет труба", "протечка", "утечка воды",
        "капает", "капает вода", "лопнула труба", "сломалась труба",
        "засор", "засорилась труба", "засор канализации",
        "унитаз засорился", "засорился унитаз", "раковина", "мойка",
        "кран", "смеситель", "душ", "слив", "сифон",
        "насос", "водяной насос", "слабый напор", "нет воды",
        "грязная вода", "запах канализации", "обратный поток",

        # Hindi / Hinglish
        "paani", "plumber", "pipe leak", "pipe toot gaya", "paani leak",
        "nal leak", "tap leak", "faucet leak", "drain block",
        "toilet block", "toilet clogged", "sink block", "basin block",
        "water pump", "pump kharab", "paani nahi aa raha",
        "paani pressure kam", "bad smell", "sewer smell",
        "पानी", "प्लंबर", "पाइप", "लीक", "नल", "टॉयलेट", "सिंक",
        "ड्रेन", "नाली", "पानी की मोटर", "पंप", "कम पानी",

        # French
        "plomberie", "plombier", "réparation plomberie", "reparation plomberie",
        "eau", "tuyau", "fuite", "fuite d'eau", "tuyau qui fuit",
        "robinet", "mitigeur", "douche", "lavabo", "évier", "evier",
        "toilette bouchée", "toilette bouchee", "wc bouché", "wc bouche",
        "canalisation bouchée", "canalisation bouchee",
        "évacuation", "evacuation", "siphon", "pompe à eau", "pompe a eau",
        "chauffe-eau", "faible pression", "pas d'eau",
        "mauvaise odeur", "odeur d'égout", "odeur d'egout",
    ],

    "máy lạnh": [
        # Vietnamese / no-accent
        "máy lạnh", "may lanh", "điều hòa", "dieu hoa", "điện lạnh", "dien lanh",
        "sửa máy lạnh", "sua may lanh", "thợ máy lạnh", "tho may lanh",
        "máy lạnh không lạnh", "may lanh khong lanh",
        "không mát", "khong mat", "không lạnh", "khong lanh",
        "kém lạnh", "kem lanh", "lạnh yếu", "lanh yeu",
        "chảy nước", "chay nuoc", "nhỏ nước", "nho nuoc",
        "máy lạnh nhỏ nước", "may lanh nho nuoc",
        "máy lạnh chảy nước", "may lanh chay nuoc",
        "nạp gas", "nap gas", "bơm gas", "bom gas", "xì gas", "xi gas",
        "thiếu gas", "thieu gas", "hết gas", "het gas",
        "vệ sinh máy lạnh", "ve sinh may lanh", "rửa máy lạnh", "rua may lanh",
        "tháo lắp máy lạnh", "thao lap may lanh", "di dời máy lạnh", "di doi may lanh",
        "cục nóng", "cuc nong", "cục lạnh", "cuc lanh",
        "block", "lốc", "loc", "hư block", "hu block", "hư lốc", "hu loc",
        "hư board", "hu board", "bo mạch", "bo mach",
        "chớp đèn", "chop den", "báo lỗi", "bao loi",
        "bám tuyết", "bam tuyet", "đóng tuyết", "dong tuyet",
        "kêu to", "keu to", "ồn", "on", "rung lắc", "rung lac",
        "tủ lạnh", "tu lanh", "máy giặt", "may giat",
        "không vắt", "khong vat", "không xả", "khong xa", "không đông đá", "khong dong da",

        # English
        "air conditioner", "air conditioning", "ac", "a/c", "ac repair",
        "aircon", "aircon repair", "cooling", "cooling repair",
        "ac not cold", "air conditioner not cold", "not cooling",
        "weak cooling", "poor cooling", "warm air", "hot air",
        "ac leaking water", "water dripping from ac", "ac dripping",
        "gas refill", "refrigerant refill", "low gas", "gas leak",
        "clean ac", "ac cleaning", "ac maintenance", "aircon maintenance",
        "install ac", "ac installation", "move ac", "relocate ac",
        "outdoor unit", "indoor unit", "compressor", "ac compressor",
        "control board", "error code", "blinking light",
        "frozen coil", "ice buildup", "noisy ac", "vibration",
        "refrigerator", "fridge", "washing machine", "washer",
        "not spinning", "not draining", "not freezing",

        # Russian
        "кондиционер", "ремонт кондиционера", "кондиционер не охлаждает",
        "не холодит", "плохо охлаждает", "дует теплым",
        "течет кондиционер", "капает кондиционер", "вода из кондиционера",
        "заправка фреоном", "фреон", "утечка фреона",
        "чистка кондиционера", "обслуживание кондиционера",
        "установка кондиционера", "перенос кондиционера",
        "наружный блок", "внутренний блок", "компрессор",
        "плата управления", "ошибка кондиционера", "мигает лампа",
        "обмерзает", "лед на кондиционере", "шумит кондиционер",
        "холодильник", "стиральная машина", "не отжимает", "не сливает",

        # Hindi / Hinglish
        "ac", "air conditioner", "ac repair", "ac service",
        "ac thanda nahi kar raha", "ac cooling nahi kar raha",
        "ac me cooling kam hai", "ac garam hawa de raha",
        "ac se paani tapak raha", "ac water leak",
        "gas bharna", "gas refill", "gas leak", "ac gas khatam",
        "ac cleaning", "ac maintenance", "ac install", "ac shift",
        "outdoor unit", "indoor unit", "compressor", "ac board",
        "error aa raha", "light blink ho rahi",
        "fridge", "refrigerator", "washing machine",
        "machine spin nahi kar rahi", "drain nahi ho raha",
        "एसी", "कूलिंग", "ठंडा नहीं", "गैस", "कंप्रेसर", "फ्रिज", "वॉशिंग मशीन",

        # French
        "climatisation", "climatiseur", "réparation climatisation",
        "reparation climatisation", "clim", "clim ne refroidit pas",
        "climatiseur ne refroidit pas", "pas froid", "air chaud",
        "fuite d'eau clim", "clim qui fuit", "eau qui coule",
        "recharge gaz", "recharge réfrigérant", "recharge refrigerant",
        "fuite de gaz", "manque de gaz",
        "nettoyage clim", "entretien clim", "maintenance clim",
        "installation clim", "déplacer clim", "deplacer clim",
        "unité extérieure", "unite exterieure", "unité intérieure", "unite interieure",
        "compresseur", "carte électronique", "carte electronique",
        "code erreur", "voyant clignote", "givre", "bruit clim",
        "réfrigérateur", "refrigerateur", "frigo", "machine à laver", "machine a laver",
    ],

    "xây dựng": [
        # Vietnamese / no-accent
        "xây dựng", "xay dung", "sửa nhà", "sua nha", "cải tạo", "cai tao",
        "cải tạo nhà", "cai tao nha", "thợ hồ", "tho ho",
        "phòng bếp", "phong bep", "phòng tắm", "phong tam", "phòng khách", "phong khach",
        "sơn", "son", "sơn nhà", "son nha", "sơn lại", "son lai",
        "chống thấm", "chong tham", "thấm", "tham", "thấm dột", "tham dot",
        "dột", "dot", "dột mái", "dot mai", "mái dột", "mai dot",
        "thấm trần", "tham tran", "thấm tường", "tham tuong",
        "nhà vệ sinh thấm", "nha ve sinh tham", "nước ngấm", "nuoc ngam",
        "ốp lát", "op lat", "gạch", "gach", "lát gạch", "lat gach",
        "ốp gạch", "op gach", "cán nền", "can nen",
        "nứt tường", "nut tuong", "nứt", "nut", "nứt chân chim", "nut chan chim",
        "bong tróc", "bong troc", "ố vàng", "o vang",
        "trát vữa", "trat vua", "xây tô", "xay to",
        "đập phá", "dap pha", "tháo dỡ", "thao do",
        "mái tôn", "mai ton", "lợp tôn", "lop ton",
        "máng xối", "mang xoi", "ban công", "ban cong",
        "chống nóng", "chong nong", "bắn silicon", "ban silicon",

        # English
        "construction", "home renovation", "renovation", "house repair",
        "home repair", "remodeling", "remodelling", "civil work",
        "masonry", "mason", "painting", "wall painting", "repainting",
        "waterproofing", "leak proofing", "roof leak", "leaking roof",
        "water seepage", "wall seepage", "ceiling seepage",
        "bathroom leakage", "bathroom waterproofing",
        "tiling", "tile work", "floor tile", "wall tile",
        "cracked wall", "wall crack", "hairline crack",
        "peeling paint", "yellow stain", "plastering",
        "cement work", "demolition", "dismantling",
        "metal roof", "tin roof", "gutter", "balcony repair",
        "heat insulation", "silicone sealing",

        # Russian
        "строительство", "ремонт дома", "ремонт квартиры", "ремонт",
        "реконструкция", "отделка", "мастер", "малярные работы",
        "покраска", "покраска стен", "гидроизоляция",
        "протекает крыша", "течет крыша", "протечка потолка",
        "протечка стены", "влага в стене", "сырость",
        "ремонт ванной", "гидроизоляция ванной",
        "плитка", "укладка плитки", "трещина в стене",
        "трещины", "отслоилась краска", "штукатурка",
        "цементные работы", "демонтаж", "разборка",
        "металлическая крыша", "водосток", "балкон",

        # Hindi / Hinglish
        "construction", "renovation", "ghar repair", "ghar renovation",
        "painting", "wall paint", "paint karna", "waterproofing",
        "seelan", "wall seepage", "roof leak", "chhat leak",
        "bathroom leakage", "tile work", "tiles lagana",
        "wall crack", "deewar crack", "plaster", "cement work",
        "tod phod", "demolition", "balcony repair", "gutter",
        "घर मरम्मत", "निर्माण", "पेंट", "दीवार", "सीलन", "छत", "टाइल",
        "दरार", "प्लास्टर", "सीमेंट",

        # French
        "construction", "rénovation", "renovation", "réparation maison",
        "reparation maison", "travaux", "maçonnerie", "maconnerie",
        "peinture", "peinture murale", "repeindre",
        "étanchéité", "etancheite", "infiltration d'eau",
        "fuite toiture", "toit qui fuit", "humidité mur", "humidite mur",
        "infiltration plafond", "salle de bain qui fuit",
        "carrelage", "pose carrelage", "fissure mur", "fissure",
        "peinture écaillée", "peinture ecaillee", "plâtrerie", "platrerie",
        "ciment", "démolition", "demolition", "démontage", "demontage",
        "gouttière", "gouttiere", "balcon", "isolation chaleur",
    ],

    "thạch cao": [
        # Vietnamese / no-accent
        "thạch cao", "thach cao", "trần thạch cao", "tran thach cao",
        "vách thạch cao", "vach thach cao", "vách ngăn", "vach ngan",
        "trần giả", "tran gia",
        "trần thả", "tran tha", "trần chìm", "tran chim",
        "thi công thạch cao", "thi cong thach cao",
        "làm trần", "lam tran", "làm vách", "lam vach",
        "khung xương", "khung xuong", "ty treo",
        "thạch cao chống ẩm", "thach cao chong am",
        "thạch cao cách âm", "thach cao cach am",
        "vách cách âm", "vach cach am",
        "sệ trần", "se tran", "võng trần", "vong tran",
        "nứt trần", "nut tran", "thủng trần", "thung tran",
        "lủng lỗ", "lung lo", "vá trần", "va tran",
        "mốc thạch cao", "moc thach cao",
        "khoét lỗ đèn", "khoet lo den", "bả matit", "ba matit",

        # English
        "drywall", "gypsum", "gypsum board", "plasterboard",
        "gypsum ceiling", "drywall ceiling", "false ceiling",
        "suspended ceiling", "drop ceiling", "ceiling partition",
        "drywall partition", "gypsum partition", "partition wall",
        "soundproof partition", "acoustic partition",
        "moisture resistant gypsum", "ceiling frame",
        "ceiling sagging", "sagging ceiling", "cracked ceiling",
        "ceiling crack", "hole in ceiling", "patch ceiling",
        "drywall repair", "gypsum repair", "putty", "skim coat",

        # Russian
        "гипсокартон", "гкл", "потолок из гипсокартона",
        "перегородка из гипсокартона", "подвесной потолок",
        "фальшпотолок", "перегородка", "звукоизоляционная перегородка",
        "каркас потолка", "провис потолок", "трещина в потолке",
        "дырка в потолке", "ремонт гипсокартона", "шпаклевка",
        "влагостойкий гипсокартон",

        # Hindi / Hinglish
        "gypsum", "gypsum board", "false ceiling", "drywall",
        "gypsum ceiling", "partition wall", "gypsum partition",
        "soundproof partition", "ceiling repair", "ceiling crack",
        "ceiling hole", "putty work", "pop ceiling",
        "जिप्सम", "फॉल्स सीलिंग", "सीलिंग", "पार्टिशन", "दीवार पार्टिशन",

        # French
        "placo", "plaque de plâtre", "plaque de platre", "plâtre", "platre",
        "faux plafond", "plafond suspendu", "cloison placo",
        "cloison sèche", "cloison seche", "cloison en plâtre",
        "cloison en platre", "cloison acoustique", "isolation acoustique",
        "plafond fissuré", "plafond fissure", "plafond affaissé",
        "plafond affaisse", "trou plafond", "réparation placo",
        "reparation placo", "enduit", "mastic",
    ],

    "sửa chữa": [
        # Vietnamese / no-accent
        "sửa", "sua", "sửa chữa", "sua chua", "hỏng", "hong",
        "hư", "hu", "lỗi", "loi", "bị lỗi", "bi loi",
        "khắc phục", "khac phuc", "kiểm tra", "kiem tra",
        "bảo trì", "bao tri", "bảo dưỡng", "bao duong",
        "thay mới", "thay moi", "lắp đặt", "lap dat",
        "sửa giúp", "sua giup", "co sua duoc khong", "có sửa được không",

        # English
        "repair", "fix", "service", "maintenance", "check",
        "inspection", "install", "installation", "replace", "replacement",
        "broken", "not working", "issue", "problem", "fault", "malfunction",
        "can you fix", "need repair", "send technician",

        # Russian
        "ремонт", "починить", "исправить", "обслуживание",
        "проверить", "диагностика", "установка", "замена",
        "сломался", "не работает", "проблема", "неисправность",
        "вызвать мастера", "нужен мастер",

        # Hindi / Hinglish
        "repair", "fix", "service", "maintenance", "check karna",
        "install", "replace", "kharab", "kaam nahi kar raha",
        "problem hai", "issue hai", "technician bhejo",
        "mechanic bhejo", "मरम्मत", "ठीक करना", "खराब", "समस्या",

        # French
        "réparer", "reparer", "réparation", "reparation", "dépannage",
        "depannage", "maintenance", "entretien", "vérifier", "verifier",
        "diagnostic", "installer", "installation", "remplacer", "remplacement",
        "en panne", "ne fonctionne pas", "problème", "probleme",
        "envoyer un technicien",
    ],

    "giá": [
        # Vietnamese / no-accent
        "giá", "gia", "báo giá", "bao gia", "bao nhiêu", "bao nhieu",
        "chi phí", "chi phi", "phí", "phi", "tiền", "tien",
        "hết bao nhiêu", "het bao nhieu", "hết mấy", "het may",
        "tốn bao nhiêu", "ton bao nhieu", "tốn kém", "ton kem",
        "bảng giá", "bang gia", "giá tham khảo", "gia tham khao",
        "giá dịch vụ", "gia dich vu", "tổng bill", "tong bill",
        "ngân sách", "ngan sach", "thiệt hại", "thiet hai",

        # English
        "price", "pricing", "cost", "fee", "charge", "charges",
        "how much", "how much does it cost", "quote", "quotation",
        "estimate", "estimated cost", "service fee", "repair cost",
        "price list", "rate", "budget", "bill", "total cost",

        # Russian
        "цена", "стоимость", "сколько стоит", "сколько будет стоить",
        "расценки", "прайс", "смета", "оценка стоимости",
        "стоимость ремонта", "цена ремонта", "тариф", "оплата",
        "сколько денег", "бюджет", "счет",

        # Hindi / Hinglish
        "price", "cost", "charge", "kitna", "kitna lagega",
        "kitne paise", "rate", "quotation", "estimate", "budget",
        "repair cost", "service charge", "bill kitna",
        "कीमत", "कितना", "खर्च", "चार्ज", "रेट", "बजट",

        # French
        "prix", "tarif", "coût", "cout", "combien", "combien ça coûte",
        "combien ca coute", "devis", "estimation", "frais",
        "frais de service", "coût réparation", "cout reparation",
        "tarification", "budget", "facture",
    ],

    "khuyến mãi": [
        # Vietnamese / no-accent
        "khuyến mãi", "khuyen mai", "ưu đãi", "uu dai",
        "giảm giá", "giam gia", "mã giảm giá", "ma giam gia",
        "voucher", "coupon", "mã code", "ma code", "code giảm", "code giam",
        "bớt", "bot", "chiết khấu", "chiet khau",
        "sale", "deal", "combo", "ưu đãi hôm nay", "uu dai hom nay",

        # English
        "promotion", "promo", "discount", "discount code",
        "coupon", "voucher", "offer", "deal", "special offer",
        "sale", "cashback", "rebate", "reduction", "promo code",

        # Russian
        "скидка", "акция", "промокод", "купон", "ваучер",
        "спецпредложение", "предложение", "распродажа",
        "бонус", "скидочный код",

        # Hindi / Hinglish
        "discount", "promo", "promotion", "coupon", "voucher",
        "offer", "deal", "discount code", "promo code",
        "chhoot", "code hai kya", "koi offer",
        "छूट", "ऑफर", "कूपन", "प्रोमो कोड",

        # French
        "promotion", "promo", "réduction", "reduction",
        "code promo", "code réduction", "code reduction",
        "coupon", "bon de réduction", "bon de reduction",
        "offre", "remise", "rabais", "voucher",
    ],

    "bảo hành": [
        # Vietnamese / no-accent
        "bảo hành", "bao hanh", "cam kết", "cam ket",
        "đảm bảo", "dam bao", "trách nhiệm", "trach nhiem",
        "đền bù", "den bu", "đền tiền", "den tien",
        "hư lại", "hu lai", "hỏng lại", "hong lai",
        "quay lại sửa", "quay lai sua", "sửa lại", "sua lai",
        "bảo đảm", "bao dam", "chắc chắn", "chac chan",

        # English
        "warranty", "guarantee", "guaranteed", "commitment",
        "responsibility", "compensation", "refund", "money back",
        "fix again", "come back to repair", "repair warranty",
        "service warranty", "100% guarantee",

        # Russian
        "гарантия", "гарантировать", "обязательство",
        "ответственность", "компенсация", "возврат денег",
        "исправить повторно", "повторный ремонт",
        "гарантийный ремонт", "сто процентов гарантии",

        # Hindi / Hinglish
        "warranty", "guarantee", "guaranteed", "zimmedari",
        "compensation", "refund", "paise wapas",
        "phir se repair", "dobara repair", "service warranty",
        "100 percent guarantee",
        "गारंटी", "वारंटी", "जिम्मेदारी", "मुआवजा", "रिफंड",

        # French
        "garantie", "garantir", "engagement", "responsabilité",
        "responsabilite", "compensation", "remboursement",
        "réparer à nouveau", "reparer a nouveau",
        "service après-vente", "service apres-vente",
        "garantie réparation", "garantie reparation",
    ],

    "khẩn cấp": [
        # Vietnamese / no-accent
        "khẩn cấp", "khan cap", "gấp", "gap", "rất gấp", "rat gap",
        "ngay", "ngay lập tức", "ngay lap tuc",
        "bây giờ", "bay gio", "liền", "lien", "tới liền", "toi lien",
        "cứu", "cuu", "cứu với", "cuu voi",
        "nguy hiểm", "nguy hiem", "không an toàn", "khong an toan",
        "cháy", "chay", "nổ", "no", "tóe lửa", "toe lua",
        "rò gas", "ro gas", "mùi gas", "mui gas",

        # English
        "urgent", "emergency", "asap", "right now", "immediately",
        "send now", "come now", "need help now", "dangerous",
        "unsafe", "fire", "burning", "explosion", "sparks",
        "gas leak", "smell gas", "electrical hazard",

        # Russian
        "срочно", "экстренно", "авария", "немедленно",
        "прямо сейчас", "нужна помощь", "опасно",
        "небезопасно", "пожар", "горит", "взрыв",
        "искры", "утечка газа", "запах газа",

        # Hindi / Hinglish
        "urgent", "emergency", "jaldi", "abhi", "abhi chahiye",
        "turant", "asap", "danger", "dangerous", "khatra",
        "unsafe", "fire", "spark", "gas leak", "gas smell",
        "help karo", "bachao",
        "तुरंत", "आपातकाल", "जल्दी", "खतरा", "आग", "गैस लीक",

        # French
        "urgent", "urgence", "immédiatement", "immediatement",
        "tout de suite", "maintenant", "au plus vite",
        "dangereux", "danger", "pas sûr", "pas sur",
        "incendie", "feu", "étincelles", "etincelles",
        "fuite de gaz", "odeur de gaz",
    ],
}


# ── Service vs Info Classification ─────────────────────────────────────────────

SERVICE_GROUPS = {
    "điện", "nước", "máy lạnh", "xây dựng", "thạch cao"
}

INFO_GROUPS = {
    "khuyến mãi", "bảo hành"
}

IGNORED_GROUPS = {
    "sửa chữa", "giá", "khẩn cấp"
}


def is_multi_question_by_lexicon(query: str) -> bool:
    """
    Xác định query có phải Multi-question dựa vào logic Chủ thể - Bổ trợ.

    Multi-question chỉ xảy ra khi:
    1. Multiple Services: > 1 dịch vụ khác nhau
       Ví dụ: "sửa ống nước với thay bóng đèn" -> nước + điện -> Multi

    2. Service + Multiple Infos: 1 dịch vụ + > 1 thông tin phụ
       Ví dụ: "máy lạnh xài voucher được không lỡ hư lại có đền không"
               -> máy_lạnh (service) + khuyến_mãi + bảo_hành (2 infos) -> Multi

    Single-question (Hợp lệ):
    - "sửa máy lạnh bao nhiêu tiền" -> 1 service + 0 info
    - "máy lạnh xài voucher được không" -> 1 service + 1 info

    Returns: True if Multi-question, False if Single-question
    """
    query_lower = query.lower()

    # Tìm tất cả service groups và info groups xuất hiện trong query
    services_found = set()
    infos_found = set()

    for service_group, keywords in FIXAGO_SYNONYMS.items():
        if service_group in IGNORED_GROUPS:
            continue

        for keyword in keywords:
            if keyword.lower() in query_lower:
                if service_group in SERVICE_GROUPS:
                    services_found.add(service_group)
                elif service_group in INFO_GROUPS:
                    infos_found.add(service_group)
                break

    # Xác định Multi-question
    # Case 1: Multiple services (> 1)
    if len(services_found) > 1:
        return True

    # Case 2: 1 service + multiple infos (> 1)
    if len(services_found) == 1 and len(infos_found) > 1:
        return True

    # Single-question: Các trường hợp khác
    return False


def get_service_and_info_counts(query: str) -> tuple:
    """
    Trả về (service_count, info_count) để debug/log.

    Ví dụ:
    - "sửa máy lạnh bao nhiêu?" -> (1, 0)
    - "máy lạnh voucher bảo hành" -> (1, 2)
    - "nước và điện" -> (2, 0)
    """
    query_lower = query.lower()
    services_found = set()
    infos_found = set()

    for service_group, keywords in FIXAGO_SYNONYMS.items():
        if service_group in IGNORED_GROUPS:
            continue

        for keyword in keywords:
            if keyword.lower() in query_lower:
                if service_group in SERVICE_GROUPS:
                    services_found.add(service_group)
                elif service_group in INFO_GROUPS:
                    infos_found.add(service_group)
                break

    return (len(services_found), len(infos_found))