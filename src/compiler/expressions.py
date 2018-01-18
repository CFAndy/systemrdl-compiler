
from . import type_placeholders as tp
from ..model import rdl_types
from .errors import RDLCompileError

class _Expr:
    def __init__(self, err_ctx):
        
        # Number of bits to use for this expression's evaluation
        # Only relevant for integer-like contexts
        self.expr_eval_width = None
        
        # operands of the expression
        self.op = []
        
        # Handle to Antlr object to use for error context
        self.err_ctx = err_ctx
        
    def trunc(self, v):
        mask = (1 << self.expr_eval_width) - 1
        return(v & mask)
        
    def predict_type(self):
        """
        Returns the expected type of the result of the expression
        This function shall call any child expression's predict_type()
        even if the child type is not relevant to the resulting type.
        Raises exception if input types are not compatible.
        """
        raise NotImplementedError
    
    def resolve_expr_width(self):
        """
        Each integer-like expression context is evaluated in a self-determined
        bit width.
        
        This function is called for the top-node of each expression context
        in order to determine, and propagate the context's expression width
        - Determine the context's expression width from all
          operands that do not define their own context.
        - Propagate resulting width back to those same ops
        """
        self.expr_eval_width = 1
        for op in self.op:
            w = op.get_min_eval_width()
            self.expr_eval_width = max(self.expr_eval_width, w)
        
        for op in self.op:
            op.propagate_eval_width(self.expr_eval_width)
        
    def get_min_eval_width(self):
        """
        Returns the expressions resulting integer width based on the
        self-determined expression bit-width rules
        (SystemVerilog LRM: IEEE Std 1800-2012, Table 11-21)
        """
        raise NotImplementedError
    
    def propagate_eval_width(self, w):
        """
        Sets the new expression evaluation width from the parent context
        If this expression is the beginning of a new self-determined integer
        context, then it shall override this and:
            - Ignore the value w
            - Instead, call self.resolve_expr_width() in order to continue
              resolution propagation
        """
        self.expr_eval_width = w
        for op in self.op:
            op.propagate_eval_width(w)
        
    def get_value(self):
        """
        Compute the value of the result of the expression
        Assumed that types are compatible.
        """
        raise NotImplementedError
    
#-------------------------------------------------------------------------------
class IntLiteral(_Expr):
    def __init__(self, err_ctx, val, width=64):
        super().__init__(err_ctx)
        self.val = val
        self.width = width
    
    def predict_type(self):
        return(int)
        
    def get_min_eval_width(self):
        return(self.width)
    
    def get_value(self):
        return(self.val)

#-------------------------------------------------------------------------------
class BuiltinEnumLiteral(_Expr):
    """
    Expr wrapper for builtin RDL enumeration types:
    AccessType, OnReadType, OnWriteType, AddressingType, PrecedenceType
    """
    def __init__(self, err_ctx, val):
        super().__init__(err_ctx)
        self.val = val
    
    def predict_type(self):
        return(type(self.val))
        
    def get_min_eval_width(self):
        return(1) # dont care
    
    def get_value(self):
        return(self.val)

#-------------------------------------------------------------------------------
class StringLiteral(_Expr):
    def __init__(self, err_ctx, val):
        super().__init__(err_ctx)
        self.val = val
    
    def predict_type(self):
        return(str)
        
    def get_min_eval_width(self):
        return(1) # dont care
    
    def get_value(self):
        return(self.val)

#-------------------------------------------------------------------------------
# Integer binary operators:
#   +  -  *  /  %  &  |  ^  ^~  ~^
# Normal expression context rules
class _BinaryIntExpr(_Expr):
    def __init__(self, err_ctx, l, r):
        super().__init__(err_ctx)
        self.op = [l, r]
        
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Left operand of expression is not a compatible numeric type", self.err_ctx)
        if(self.op[1].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Right operand of expression is not a compatible numeric type", self.err_ctx)
        return(int)
    
    def get_min_eval_width(self):
        return(max(
            self.op[0].get_min_eval_width(),
            self.op[1].get_min_eval_width()
        ))
        
    def get_ops(self):
        l = int(self.op[0].get_value())
        r = int(self.op[1].get_value())
        return(l,r)
    
class Add(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l + r))

class Sub(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l - r))

class Mult(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l * r))

class Div(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l // r))

class Mod(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l % r))
        
class BitwiseAnd(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l & r))
        
class BitwiseOr(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l | r))
        
class BitwiseXor(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l ^ r))

class BitwiseXnor(_BinaryIntExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l ^~ r))

#-------------------------------------------------------------------------------
# Integer unary operators:
#   +  -  ~
# Normal expression context rules
class _UnaryIntExpr(_Expr):
    def __init__(self, err_ctx, n):
        super().__init__(err_ctx)
        self.op = [n]
        
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Operand of expression is not a compatible numeric type", self.err_ctx)
        return(int)
    
    def get_min_eval_width(self):
        return(self.op[0].get_min_eval_width())
        
    def get_ops(self):
        n = int(self.op[0].get_value())
        return(n)

class UnaryPlus(_UnaryIntExpr):
    def get_value(self):
        n = self.get_ops()
        return(self.trunc(n))

class UnaryMinus(_UnaryIntExpr):
    def get_value(self):
        n = self.get_ops()
        return(self.trunc(-n))

class BitwiseInvert(_UnaryIntExpr):
    def get_value(self):
        n = self.get_ops()
        return(self.trunc(~n))

#-------------------------------------------------------------------------------
# Relational operators:
#   == != < > <= >=
# Result is always 1 bit bool
# Creates a new evaluation context
# Child operands are evaluated in the same width context, sized to the max
# of either op.
class _RelationalExpr(_Expr):
    def __init__(self, err_ctx, l, r):
        super().__init__(err_ctx)
        self.op = [l, r]
        print("TODO: add support for non-numeric comparisons")
        
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Left operand of expression is not a compatible numeric type", self.err_ctx)
        if(self.op[1].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Right operand of expression is not a compatible numeric type", self.err_ctx)
        return(bool)
    
    def get_min_eval_width(self):
        return(1)
        
    def propagate_eval_width(self, w):
        """
        Ignore parent's width and start a new expression context
        """
        self.resolve_expr_width()
        
    def get_ops(self):
        l = int(self.op[0].get_value())
        r = int(self.op[1].get_value())
        return(l,r)
        
class Eq(_RelationalExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l == r)

class Neq(_RelationalExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l != r)

class Lt(_RelationalExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l < r)
        
class Gt(_RelationalExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l > r)

class Leq(_RelationalExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l <= r)

class Geq(_RelationalExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l >= r)

#-------------------------------------------------------------------------------
# Reduction operators:
#   &  ~&  |  ~|  ^  ^~  !
# Result is always 1 bit bool
# Creates a new evaluation context
class _ReductionExpr(_Expr):
    def __init__(self, err_ctx, n):
        super().__init__(err_ctx)
        self.op = [n]
    
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Operand of expression is not a compatible numeric type", self.err_ctx)
        return(int)
    
    def get_min_eval_width(self):
        return(1)
        
    def propagate_eval_width(self, w):
        """
        Ignore parent's width and start a new expression context
        """
        self.resolve_expr_width()
        
    def get_ops(self):
        n = int(self.op[0].get_value())
        return(n)

class AndReduce(_ReductionExpr):
    def get_value(self):
        n = self.get_ops()
        n = self.trunc(~n)
        return(int(n == 0))
        
class NandReduce(_ReductionExpr):
    def get_value(self):
        n = self.get_ops()
        return(int(n != 0))
        
class OrReduce(_ReductionExpr):
    def get_value(self):
        n = self.get_ops()
        return(int(n != 0))
        
class NorReduce(_ReductionExpr):
    def get_value(self):
        n = self.get_ops()
        return(int(n == 0))

class XorReduce(_ReductionExpr):
    def get_value(self):
        n = self.get_ops()
        v = 0
        while(n):
            if(n & 1):
                v ^= 1
            n >>= 1
        return(v)

class XnorReduce(_ReductionExpr):
    def get_value(self):
        n = self.get_ops()
        v = 1
        while(n):
            if(n & 1):
                v ^= 1
            n >>= 1
        return(v)
        
class BoolNot(_ReductionExpr):
    def get_value(self):
        return(not self.op[0])

#-------------------------------------------------------------------------------
# Logical boolean operators:
#   && ||
# Both operands are self-determined
class _BoolExpr(_Expr):
    def __init__(self, err_ctx, l, r):
        super().__init__(err_ctx)
        self.op = [l,r]
    
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Left operand of expression is not a compatible boolean type", self.err_ctx)
        if(self.op[1].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Right operand of expression is not a compatible boolean type", self.err_ctx)
        return(bool)
    
    def resolve_expr_width(self):
        # All operands are self determined. Do nothing
        pass
    
    def get_min_eval_width(self):
        return(1)
    
    def propagate_eval_width(self, w):
        """
        Eval width is ignored. Trigger expression width
        resolution for both operand since they are self-determined
        """
        self.op[0].resolve_expr_width()
        self.op[1].resolve_expr_width()
    
    def get_ops(self):
        l = bool(self.op[0].get_value())
        r = bool(self.op[1].get_value())
        return(l,r)
        
class BoolAnd(_BoolExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l and r)
        
class BoolOr(_BoolExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(l or r)
        
#-------------------------------------------------------------------------------
# Exponent & shift operators:
#   **  <<  >>
# Righthand operand is self-determined
class _ExpShiftExpr(_Expr):
    def __init__(self, err_ctx, l, r):
        super().__init__(err_ctx)
        self.op = [l,r]
    
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Left operand of expression is not a compatible numeric type", self.err_ctx)
        if(self.op[1].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Right operand of expression is not a compatible numeric type", self.err_ctx)
        return(int)
    
    def resolve_expr_width(self):
        """
        Eval width only depends on the first operand
        """
        self.expr_eval_width = self.op[0].get_min_eval_width()
        self.op[0].propagate_eval_width(self.expr_eval_width)
    
    def get_min_eval_width(self):
        # Righthand op has no influence in evaluation context
        return(self.op[0].get_min_eval_width())
    
    def propagate_eval_width(self, w):
        """
        Propagate eval width as usual, but also trigger expression width
        resolution for righthand operand since it is self-determined
        """
        self.expr_eval_width = w
        self.op[0].propagate_eval_width(w)
        
        self.op[1].resolve_expr_width()
    
    def get_ops(self):
        l = int(self.op[0].get_value())
        r = int(self.op[1].get_value())
        return(l,r)
    
class Exponent(_ExpShiftExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(int(l ** r)))

class LShift(_ExpShiftExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l << r))

class RShift(_ExpShiftExpr):
    def get_value(self):
        l,r = self.get_ops()
        return(self.trunc(l >> r))

#-------------------------------------------------------------------------------
# Ternary conditional operator
#   i ? j : k
# Truth expression is self-determined and does not contribute to context

class TernaryExpr(_Expr):
    def __init__(self, err_ctx, i, j, k):
        super().__init__(err_ctx)
        self.op = [i, j, k]
    
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Conditional operand of expression is not a compatible boolean type", self.err_ctx)
        
        # Type of j and k shall be compatible
        t_j = self.op[1].predict_type()
        t_k = self.op[2].predict_type()
        
        num_t = [int, bool]
        if((t_j in num_t) and (t_k in num_t)):
            # Both are a numeric type
            return(int)
        else:
            # Not numeric types. Shall be equal types
            if(t_j != t_k):
                raise RDLCompileError("True/False results of ternary conditional are not compatible types", self.err_ctx)
            return(t_j)
    
    def resolve_expr_width(self):
        wj = self.op[1].get_min_eval_width()
        wk = self.op[2].get_min_eval_width()
        self.expr_eval_width = max(1, wj, wk)
        
        self.op[1].propagate_eval_width(self.expr_eval_width)
        self.op[2].propagate_eval_width(self.expr_eval_width)
    
    def get_min_eval_width(self):
        # Truth operand has no influence in evaluation context
        return(max(
            self.op[1].get_min_eval_width(),
            self.op[2].get_min_eval_width()
        ))
    
    def propagate_eval_width(self, w):
        """
        Propagate eval width as usual, but also trigger expression width
        resolution for truth operand since it is self-determined
        """
        self.expr_eval_width = w
        self.op[1].propagate_eval_width(w)
        self.op[2].propagate_eval_width(w)
        
        self.op[0].resolve_expr_width()
    
    def get_value(self):
        i = bool(self.op[0].get_value())
        j = self.op[1].get_value()
        k = self.op[2].get_value()
        
        if(i):
            return(j)
        else:
            return(k)

#-------------------------------------------------------------------------------
# Width cast operator
# the cast type informs the parser what width to cast to
# The cast width determines the result's width
# Also influences the min eval width of the value expression
class WidthCast(_Expr):
    def __init__(self, err_ctx, v, w_expr=None, w_int=64):
        super().__init__(err_ctx)
        
        if(w_expr is not None):
            self.op = [v, w_expr]
            self.cast_width = None
        else:
            self.op = [v]
            self.cast_width = w_int
        
    def predict_type(self):
        if(self.cast_width is None):
            if(self.op[1].predict_type() not in [int, bool, tp.Bit]):
                raise RDLCompileError("Width operand of cast expression is not a compatible numeric type", self.err_ctx)
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Value operand of cast expression cannot be cast to an integer", self.err_ctx)
        
        return(int)
    
    def resolve_expr_width(self):
        self.resolve_cast_width()
        self.expr_eval_width = self.cast_width
        w = self.op[0].get_min_eval_width()
        self.expr_eval_width = max(self.expr_eval_width, w)
        self.op[0].propagate_eval_width(self.expr_eval_width)
    
    def get_min_eval_width(self):
        self.resolve_cast_width()
        return(self.cast_width)
        
    def propagate_eval_width(self, w):
        """
        Ignore parent's width and start a new expression context using
        the cast's width
        """
        self.resolve_expr_width()
    
    def resolve_cast_width(self):
        if(self.cast_width is None):
            # Need to force evaluation of the width value in order to proceed
            self.op[1].resolve_expr_width()
            self.cast_width = self.op[1].get_value()
    
    def get_value(self):
        # Truncate to cast width instead of eval width
        n = int(self.op[0].get_value())
        self.expr_eval_width = self.cast_width
        return(self.trunc(n))

#-------------------------------------------------------------------------------
# Boolean cast operator

class BoolCast(_Expr):
    def __init__(self, err_ctx, n):
        super().__init__(err_ctx)
        self.op = [n]
    
    def predict_type(self):
        if(self.op[0].predict_type() not in [int, bool, tp.Bit]):
            raise RDLCompileError("Value operand of cast expression cannot be cast to a boolean", self.err_ctx)
        return(bool)
    
    def get_min_eval_width(self):
        return(1)
        
    def propagate_eval_width(self, w):
        """
        Ignore parent's width and start a new expression context
        """
        self.resolve_expr_width()
        
    def get_value(self):
        n = int(self.op[0].get_value())
        return(n != 0)

#-------------------------------------------------------------------------------
# Assignment cast
# This is a wrapper expression that normalizes the expression result
# to the expected data type
# This wrapper forces the operand to be evaluated in a self-determined context
# The cast type has no effect on expression evaluation
# During post-compile:
#   Checks that the expression result is of a compatible type
#
# When getting value:
#   Ensures that the expression result gets converted to the resulting type
class AssignmentCast(_Expr):
    def __init__(self, err_ctx, v, dest_type):
        super().__init__(err_ctx)
        
        self.op = [v]
        self.dest_type = dest_type
    
    def predict_type(self):
        
        op_type = self.op[0].predict_type()
        
        if(self.dest_type in [int, bool, tp.Bit]):
            # Number-like types are compatible to each-other
            if(op_type not in [int, bool, tp.Bit]):
                raise RDLCompileError("Assignment is not compatible with the destination type", self.err_ctx)
        elif(self.dest_type == tp.Array):
            if(op_type != tp.Array):
                raise RDLCompileError("Assignment is not compatible with the destination type", self.err_ctx)
            
            # TODO: Check that array size and element types also match
            raise NotImplementedError
            
        elif(self.dest_type != op_type):
            # Otherwise, type shall match exactly
            raise RDLCompileError("Assignment is not compatible with the destination type", self.err_ctx)
        
        return(self.dest_type)
    
    def get_min_eval_width(self):
        return(self.op[0].get_min_eval_width())
    
    def propagate_eval_width(self, w):
        self.resolve_expr_width()
    
    def get_value(self):
        v = self.op[0].get_value()
        
        if(self.dest_type == bool):
            return(bool(v))
        elif(self.dest_type == tp.Bit):
            return(int(v) & 1)
        else:
            return(v)