import re
from typing import Any, Dict, List

from word2number import w2n
from sympy import (
    symbols,
    sympify,
    Eq,
    solve,
    diff,
    integrate,
    limit,
    Matrix,
    parse_expr,
)

WORD_OPERATORS = {
    "plus": "+",
    "minus": "-",
    "times": "*",
    "multiplied by": "*",
    "divided by": "/",
    "divide by": "/",
    "sum of": "+",
    "product of": "*",
}

ARITHMETIC_WORDS = [
    "sum", "total", "average", "mean", "calculate", "calculation",
    "add", "added", "plus", "subtract", "minus", "difference",
    "multiply", "times", "divide", "quotient", "percentage",
    "percent", "half", "double", "twice", "square", "cube",
    "solve", "equation", "derivative", "integral", "limit",
    "matrix", "determinant",
]

def _replace_word_operators(text: str) -> str:
    for phrase, symbol in WORD_OPERATORS.items():
        text = re.sub(rf"\b{re.escape(phrase)}\b", f" {symbol} ", text)
    return text


def _handle_special_phrases(text: str) -> str:
    text = re.sub(r"\bhalf of (\w+)\b", r"(\1/2)", text)
    text = re.sub(r"\btwice (\w+)\b", r"(2*\1)", text)
    text = re.sub(r"\bdouble (\w+)\b", r"(2*\1)", text)

    text = re.sub(r"(\w+) squared\b", r"\1**2", text)
    text = re.sub(r"(\w+) cubed\b", r"\1**3", text)

    return text


def _words_to_number(text: str) -> str:
    tokens = text.split()
    out: List[str] = []
    buffer: List[str] = []

    def flush_buffer():
        nonlocal buffer
        if not buffer:
            return
        try:
            out.append(str(w2n.word_to_num(" ".join(buffer))))
        except Exception:
            out.extend(buffer)       
        buffer = []

    for token in tokens:
        if token.isalpha() and token not in WORD_OPERATORS:
            buffer.append(token)
        else:
            flush_buffer()
            out.append(token)

    flush_buffer()
    return " ".join(out)


def normalize_expression(text: str) -> str:
    txt = text.lower()
    txt = _replace_word_operators(txt)
    txt = _handle_special_phrases(txt)
    txt = _words_to_number(txt)
    return txt

def insert_multiplication(expr: str) -> str:
    expr = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", expr)     
    expr = re.sub(r"([a-zA-Z])([a-zA-Z])", r"\1*\2", expr) 
    expr = re.sub(r"(\d)\s*\(", r"\1*(", expr)           
    expr = re.sub(r"\)(\s*[a-zA-Z])", r")*\1", expr)      
    return expr

def words_to_math(text: str) -> str:
    txt = normalize_expression(text)
    txt = insert_multiplication(txt)

    txt = re.sub(r"sum of (\w+) and (\w+)", r"\1+\2", txt)
    txt = re.sub(r"product of (\w+) and (\w+)", r"\1*\2", txt)

    return txt

def _handle_derivative(expr: str) -> Any:
    m = re.search(r"derivative of (.+?) w\.?r\.?t (\w+)", expr)
    if not m:
        return None
    f = parse_expr(m.group(1))
    var = symbols(m.group(2))
    return diff(f, var).evalf()

def _handle_integral(expr: str) -> Any:
    m = re.search(r"integral of (.+?) w\.?r\.?t (\w+)", expr)
    if not m:
        return None
    f = parse_expr(m.group(1))
    var = symbols(m.group(2))
    return integrate(f, var).evalf()

def _handle_limit(expr: str) -> Any:
    m = re.search(r"limit of (.+?) as (\w+) -> ([\d\.\+\-e]+)", expr)
    if not m:
        return None
    f = parse_expr(m.group(1))
    var = symbols(m.group(2))
    val = float(m.group(3))
    return limit(f, var, val).evalf()

def handle_calculus(expr: str) -> Any:
    if "derivative" in expr:
        return _handle_derivative(expr)
    if "integral" in expr:
        return _handle_integral(expr)
    if "limit" in expr:
        return _handle_limit(expr)
    return None

def _solve_equations(parts: List[str]) -> Dict:
    eqs = []
    for p in parts:
        if "=" in p:
            left, right = p.split("=", 1)
            eqs.append(Eq(sympify(left), sympify(right)))

    var_names = set(re.findall(r"[a-zA-Z]", " ".join(parts)))
    vars_sym = symbols(list(var_names))

    sol = solve(eqs, vars_sym, dict=True)
    if sol:
        return {k: v.evalf() if hasattr(v, "evalf") else v for k, v in sol[0].items()}
    return {}

def _handle_matrix(expr: str) -> Any:
    try:
        m = parse_expr(expr)
        if isinstance(m, Matrix):
            return m
    except Exception:
        pass
    return None

def _solve_math(raw_expr: str, mode: str = "auto") -> str:

    expr = words_to_math(raw_expr).replace("^", "**")

    parts = [p.strip() for p in re.split(r"[;,]", expr) if p.strip()]
    results: List[Any] = []

    def decide_part(p: str) -> Any:
        if "=" in p:
            return "solve"
        if any(k in p for k in ("derivative", "integral", "limit")):
            return "calc"
        if "matrix" in p.lower():
            return "matrix"
        return "eval"

    try:
        for part in parts:
            effective_mode = mode.lower()
            if effective_mode == "auto":
                effective_mode = decide_part(part)

            if effective_mode == "solve":
                sol = _solve_equations(parts)
                results.append(sol)
                break           

            if effective_mode == "calc":
                calc_res = handle_calculus(part)
                if calc_res is not None:
                    results.append(calc_res)
                    continue

            if effective_mode == "matrix":
                mat = _handle_matrix(part)
                if mat is not None:
                    results.append(mat)
                    continue

            if effective_mode == "factor":
                results.append(sympify(part).factor())
                continue

            results.append(sympify(part).evalf())

        if not results:
            return "No computable expression found."

        if len(results) == 1:
            return str(results[0])

        return str(tuple(results))

    except Exception as exc:  
        return f"Cannot solve! reason: {exc} for expression: {raw_expr}"


# PUBLIC ENTRY POINT
def run(expression: str, mode: str = "auto") -> str:
    return _solve_math(expression, mode)


# QUICK SELF‑TEST 
if __name__ == "__main__":
    tests = [
        "5 plus 7",
        "solve x + y = 35, 2*x + 4*y = 94",
        "derivative of sin(x**2) w.r.t x",
        "integral of x**2 w r t x",
        "limit of (x**2-1)/(x-1) as x -> 1",
        "matrix([[1,2],[3,4]])",
    ]
    for t in tests:
        print(f"> {t}\n{run(t)}\n")