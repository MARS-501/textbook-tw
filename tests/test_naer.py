import pytest

from textbook_tw.glossary.naer import parse_source, parse_targets


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("攻角;衝角", ("攻角", "衝角")),
        ("磨蝕；磨耗", ("磨蝕", "磨耗")),
        ("活力圈[天]", ("活力圈",)),
        ("雷諾茲數{雷諾數}", ("雷諾茲數",)),
        ("散度｛數學｝；發散量", ("散度", "發散量")),
        ("房室阻滯（心電圖）", ("房室阻滯",)),  # 詞尾兩字以上的括號是註解
        ("加速（度）梯度", ("加速度梯度",)),  # 詞中括號是可省略的字
        ("附著（力）；外聚（力）", ("附著力", "外聚力")),
        ("滯（點）壓（力）", ("滯點壓力",)),
        ("翼形;翼切面;翼形", ("翼形", "翼切面")),  # 去除重複
        ("", ()),
    ],
)
def test_parse_targets(raw, expected):
    assert parse_targets(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mach number", "Mach number"),
        ("angle of attack (AOA)", "angle of attack"),
        ("acceleration; gravitational", "gravitational acceleration"),  # 倒裝
        ("contour; Mach number", "Mach number contour"),
        ("  shock   wave ", "shock wave"),
        ("input/output", None),
        ("amplifier, operational", None),
        ("a; b; c", None),
        ("", None),
    ],
)
def test_parse_source(raw, expected):
    assert parse_source(raw) == expected
