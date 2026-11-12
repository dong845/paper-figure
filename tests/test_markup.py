from paperfig.markup import parse, to_html, plain, Run


def test_parse_sub_sup_bold():
    lines = parse("<b>x</b><sub>t</sub><sup>2</sup>")
    assert lines == [[Run("x", bold=True), Run("t", script="sub"), Run("2", script="sup")]]


def test_nested_bold_italic():
    lines = parse("<b>a<i>b</i></b>")
    assert lines == [[Run("a", bold=True), Run("b", bold=True, italic=True)]]


def test_br_makes_lines():
    assert [[r.text for r in ln] for ln in parse("Multi-Scale<br>Attention")] == [["Multi-Scale"], ["Attention"]]
    assert len(parse("a<br/>b<br />c")) == 3


def test_entities_decoded_in_runs():
    assert parse("a &lt; b &amp; c")[0][0].text == "a < b & c"


def test_literal_less_than_kept():
    assert parse("t < T")[0][0].text == "t < T"


def test_html_escapes_ampersand_lt():
    assert to_html("a & b < c") == "a &amp; b &lt; c"
    assert to_html("<b>x</b><br>y<sub>1</sub>") == "<b>x</b><br>y<sub>1</sub>"


def test_html_preserves_entities_not_double_escaped():
    assert to_html("a &lt; b") == "a &lt; b"


def test_plain_strips_tags():
    assert plain("Multi-Scale<br><b>Attention</b>") == "Multi-Scale Attention"


def test_empty_label():
    assert parse("") == [[]]
    assert to_html("") == ""
