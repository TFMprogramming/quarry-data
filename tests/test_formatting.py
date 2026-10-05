from quarry.formatting import money, percent


def test_money_below_a_million_uses_thousand_dots():
    assert money(480_000) == "480.000 $"


def test_money_millions_and_billions():
    assert money(1_234_000) == "1,2 Mio. $"
    assert money(2_400_000_000) == "2,4 Mrd. $"


def test_percent_has_sign():
    assert percent(0.476) == "+48 %"
    assert percent(-0.05) == "−5 %"
