
CITIES: list[tuple[str, str]] = [
    ("almaty", "Алматы"),
    ("astana", "Астана"),
    ("shymkent", "Шымкент"),
    ("karaganda", "Караганда"),
    ("aktobe", "Актобе"),
    ("taraz", "Тараз"),
    ("pavlodar", "Павлодар"),
    ("ust-kamenogorsk", "Усть-Каменогорск"),
    ("semey", "Семей"),
    ("atyrau", "Атырау"),
    ("kostanay", "Костанай"),
    ("kyzylorda", "Кызылорда"),
    ("uralsk", "Уральск"),
    ("petropavl", "Петропавловск"),
    ("aktau", "Актау"),
    ("temirtau", "Темиртау"),
    ("turkestan", "Туркестан"),
    ("kokshetau", "Кокшетау"),
    ("taldykorgan", "Талдыкорган"),
    ("ekibastuz", "Экибастуз"),
    ("rudny", "Рудный"),
    ("zhezkazgan", "Жезказган"),
]

CITY_BY_SLUG = dict(CITIES)

def city_name(slug: str) -> str:
    return CITY_BY_SLUG.get(slug, slug)
