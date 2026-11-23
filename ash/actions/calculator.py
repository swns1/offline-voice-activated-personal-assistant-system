"""Maths and unit conversions, worked out on this PC -- never sent to a
search engine, so they work offline and need no permission.

- "what's 15% of 80", "what is 12 times 7", "calculate 2 to the power of
  10", "what's the square root of 144", "how much is 3.5 divided by 2"
- "convert 5 miles to kilometers", "what's 100 fahrenheit in celsius",
  "how many feet are in a mile"

Web search ("what is ...") tries answer() first, so a calculation
phrased as a question never leaves the PC.

Arithmetic is evaluated by walking Python's syntax tree with a strict
whitelist -- numbers, + - * / **, unary minus, and sqrt() -- never with
eval(), and with limits on exponent and result size, so no spoken input
can run code or hang the assistant.
"""
import ast
import logging
import math
import operator
import re

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_MAX_EXPONENT = 1000
_MAX_MAGNITUDE = 1e18

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALE_WORDS = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}

# Spoken operators -> symbols, longest first so "multiplied by" isn't
# half-matched as something shorter.
_OPERATOR_WORDS = [
    ("to the power of", "**"), ("raised to", "**"), ("multiplied by", "*"), ("divided by", "/"),
    ("plus", "+"), ("minus", "-"), ("times", "*"), ("over", "/"),
    ("squared", "**2"), ("cubed", "**3"), ("×", "*"), ("÷", "/"), ("^", "**"),
]

_BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
            ast.Div: operator.truediv, ast.Pow: operator.pow}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


class _NotMaths(Exception):
    pass


# --- arithmetic ---------------------------------------------------------------

def _words_to_numbers(text: str) -> str:
    """"twenty five" -> "25", "two hundred" -> "200". Speech-to-text
    usually writes digits already; this covers the times it doesn't."""
    words, out, i = text.split(), [], 0
    while i < len(words):
        if words[i] not in _NUMBER_WORDS:
            out.append(words[i])
            i += 1
            continue
        total = current = 0
        while i < len(words) and (words[i] in _NUMBER_WORDS or words[i] in _SCALE_WORDS):
            word = words[i]
            if word in _NUMBER_WORDS:
                current += _NUMBER_WORDS[word]
            elif word == "hundred":
                current = (current or 1) * 100
            else:
                total += (current or 1) * _SCALE_WORDS[word]
                current = 0
            i += 1
        out.append(str(total + current))
    return " ".join(out)


def _to_expression(text: str) -> str | None:
    text = re.sub(r"^(the\s+)?", "", text.strip().lower())
    text = re.sub(r"\s*(equals|equal to|is equal to|=)\s*$", "", text)
    text = _words_to_numbers(text)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # "1,000"
    # "15% of 80" / "15 percent of 80" -> (15/100)*80 ; "15%" -> (15/100)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+", r"(\1/100)*", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", r"(\1/100)", text)
    text = re.sub(r"(?:the\s+)?square root of\s+(\(?[\d.]+\)?)", r"sqrt(\1)", text)
    for words, symbol in _OPERATOR_WORDS:
        text = text.replace(words, f" {symbol} ")
    text = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", text)  # "12 x 7"
    text = re.sub(r"\s+", " ", text).strip()
    if not re.fullmatch(r"[\d\s.+\-*/()]*(?:sqrt[\d\s.+\-*/()]*)*", text):
        return None
    if not re.search(r"[+\-*/]|sqrt", text) or not re.search(r"\d", text):
        return None  # just a number, or nothing: not a calculation
    return text


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > _MAX_EXPONENT or abs(left) > _MAX_MAGNITUDE):
            raise OverflowError
        result = _BIN_OPS[type(node.op)](left, right)
        if isinstance(result, complex) or abs(result) > _MAX_MAGNITUDE:
            raise OverflowError
        return result
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt"
            and len(node.args) == 1 and not node.keywords):
        value = _evaluate(node.args[0])
        if value < 0:
            raise ValueError("square root of a negative number")
        return math.sqrt(value)
    raise _NotMaths


def calculate(text: str) -> float | None:
    """The value of a spoken calculation, or None if it isn't one.
    Raises ZeroDivisionError / OverflowError / ValueError for maths that
    has no sensible answer."""
    expression = _to_expression(text)
    if expression is None:
        return None
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None
    try:
        return _evaluate(tree)
    except _NotMaths:
        return None


def format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        number = int(round(value))
        return f"{number:,}" if abs(number) >= 10_000 else str(number)
    if abs(value) >= 100:
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    return f"{value:.4g}"


# --- unit conversion ---------------------------------------------------------------

_units = None


def _ureg():
    """pint's unit registry, built on first conversion (it takes a moment).
    None if pint isn't installed -- conversions are then just unavailable."""
    global _units
    if _units is None:
        try:
            import pint
        except ImportError:
            return None
        _units = pint.UnitRegistry()
    return _units


_AMOUNT = r"(?P<amount>-?\d+(?:\.\d+)?|an?|one)"
_CONVERT_RE = re.compile(rf"^(?:convert\s+)?{_AMOUNT}\s+(?P<source>.+?)\s+(?:to|in|into)\s+(?P<dest>[a-z][a-z /]*)$")
_HOW_MANY_RE = re.compile(
    rf"^(?:how many\s+)?(?P<dest>[a-z][a-z /]*?)\s+(?:are\s+|is\s+)?(?:there\s+)?"
    rf"in\s+{_AMOUNT}\s+(?P<source>[a-z][a-z /]*)$"
)


_TEMPERATURES = {"celsius": "degrees Celsius", "centigrade": "degrees Celsius",
                 "fahrenheit": "degrees Fahrenheit", "kelvin": "kelvin"}


def _unit_name(spoken: str) -> str:
    spoken = re.sub(r"^(degrees?|a|an|the)\s+", "", spoken.strip())
    return {"centigrade": "celsius"}.get(spoken, spoken)


def _spoken_unit(spoken: str) -> str:
    """"fahrenheit" / "degrees fahrenheit" -> "degrees Fahrenheit"."""
    bare = re.sub(r"^degrees?\s+", "", spoken.strip())
    return _TEMPERATURES.get(bare, spoken)


def convert(text: str) -> str | None:
    """A spoken answer for a unit conversion, or None if it isn't one."""
    text = _words_to_numbers(text.strip().lower())
    how_many = _HOW_MANY_RE.match(text)
    match = how_many or _CONVERT_RE.match(text)
    if not match:
        return None
    amount_text = match.group("amount")
    amount = 1.0 if amount_text in ("a", "an", "one") else float(amount_text)
    source_spoken, dest_spoken = match.group("source").strip(), match.group("dest").strip()

    ureg = _ureg()
    if ureg is None:
        return None
    from pint.errors import PintError

    try:
        quantity = ureg.Quantity(amount, _unit_name(source_spoken))
        result = quantity.to(_unit_name(dest_spoken)).magnitude
    except (PintError, AttributeError, ValueError, TypeError):
        # Not units it knows ("dollars to pesos": currencies need live
        # exchange rates), or incompatible ones. Only say so if you
        # clearly asked to convert -- otherwise it's probably an ordinary
        # question ("a way to get to Manila") for web search.
        if text.startswith("convert "):
            return (f"I can't convert {source_spoken} to {dest_spoken}. "
                    "I can do units like distance, weight, volume, speed and temperature.")
        return None

    if how_many:
        return f"There are {format_number(result)} {dest_spoken} in {amount_text} {source_spoken}."
    return f"{format_number(amount)} {_spoken_unit(source_spoken)} is {format_number(result)} {_spoken_unit(dest_spoken)}."


# --- spoken answers ---------------------------------------------------------------

def answer(text: str) -> str | None:
    """A spoken answer if `text` is a calculation or unit conversion,
    otherwise None (so the caller can carry on, e.g. to web search)."""
    converted = convert(text)
    if converted:
        return converted
    try:
        value = calculate(text)
    except ZeroDivisionError:
        return "You can't divide by zero."
    except OverflowError:
        return "That number's too big for me to say."
    except ValueError:
        return "That doesn't have a real-number answer."
    if value is None:
        return None
    question = re.sub(r"\s*(equals|equal to|is equal to|=)\s*$", "", text.strip())
    reply = f"{question} is {format_number(value)}."
    return reply[0].upper() + reply[1:]


def handle_calculate(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    reply = answer(target)
    tts.say(reply or "I couldn't work that out. Try something like 'what's 15 percent of 80'.")
    return HandlerResult()


def handle_how_many(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    """"how many feet are in a mile" is a conversion; "how many people
    live in Manila" is a question for web search."""
    reply = convert(f"how many {target}")
    if reply:
        tts.say(reply)
        return HandlerResult()
    from ash.actions.search import handle_search
    return handle_search(f"how many {target}", registry, tts, log, config)
