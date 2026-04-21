"""Safe evaluator for calculator tool - AST-based math expression evaluation."""
import ast
import math
from typing import Any


class SafeEvaluator(ast.NodeVisitor):
    """AST-based safe evaluator for mathematical expressions.

    Only allows basic math operations and a limited set of functions.
    Blocks any code execution, attribute access, or dangerous operations.
    """

    SAFE_CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
    }

    SAFE_FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": pow,
        "floor": math.floor,
        "ceil": math.ceil,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "radians": math.radians,
        "degrees": math.degrees,
    }

    ALLOWED_OPS = {
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.FloorDiv,
        ast.UAdd,
        ast.USub,
    }

    def __init__(self):
        self._errors: list[str] = []

    def visit_Constant(self, node: ast.Constant) -> Any:
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.SAFE_CONSTANTS:
            return self.SAFE_CONSTANTS[node.id]
        if node.id in self.SAFE_FUNCTIONS:
            raise ValueError(f"'{node.id}' must be called as a function")
        raise ValueError(f"Unknown name: {node.id}")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if type(node.op) not in self.ALLOWED_OPS:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)
        if op_type is ast.Add:
            return left + right
        if op_type is ast.Sub:
            return left - right
        if op_type is ast.Mult:
            return left * right
        if op_type is ast.Div:
            return left / right
        if op_type is ast.Pow:
            return left ** right
        if op_type is ast.Mod:
            return left % right
        if op_type is ast.FloorDiv:
            return left // right
        raise ValueError(f"Unsupported operator: {type(node.op).__name__}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if type(node.op) not in self.ALLOWED_OPS:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError(f"Unsupported function call type: {type(node.func)}")
        func_name = node.func.id
        if func_name not in self.SAFE_FUNCTIONS:
            raise ValueError(f"Unsupported function: {func_name}")
        args = [self.visit(arg) for arg in node.args]
        return self.SAFE_FUNCTIONS[func_name](*args)

    def visit_Expr(self, node: ast.Expr) -> Any:
        return self.visit(node.value)

    def visit_Module(self, node: ast.Module) -> Any:
        if len(node.body) != 1:
            raise ValueError("Expected exactly one expression")
        return self.visit(node.body[0])


def safe_eval(expression: str) -> float:
    """Safely evaluate a mathematical expression using AST analysis.

    Args:
        expression: A string containing a math expression (e.g., "2 + 3 * 4")

    Returns:
        The result of the evaluation as a float

    Raises:
        ValueError: If the expression contains unsafe operations
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid syntax: {e}")

    evaluator = SafeEvaluator()
    result = evaluator.visit(tree.body)

    if not isinstance(result, (int, float)):
        raise ValueError(f"Expression did not evaluate to a number: {type(result)}")

    return float(result)
