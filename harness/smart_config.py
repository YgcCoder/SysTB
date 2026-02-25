"""
SmartConfig — parameter wrapper that supports all LLM-generated access patterns.

Supported patterns:
  1. config['N']                          -> 20
  2. config.get('N', default)             -> 20
  3. config['parameters']['N']            -> 20
  4. config['parameters']['N']['value']   -> 20
  5. config.get('N', {}).get('value', d)  -> 20
"""


class SmartConfig(dict):
    """
    Smart config dict that normalises nested parameter structures so
    LLM-generated strategy code works regardless of access pattern.
    """

    def __init__(self, strategy_card):
        super().__init__(strategy_card)
        self._setup_parameters()

    def _setup_parameters(self):
        if 'parameters' not in self:
            return
        params = self['parameters']
        if not isinstance(params, dict):
            return
        new_params = SmartParamDict()
        for param_name, param_value in params.items():
            actual_value = param_value['value'] if isinstance(param_value, dict) and 'value' in param_value else param_value
            new_params[param_name] = SmartValue(actual_value, param_value)
            super().__setitem__(param_name, actual_value)
        super().__setitem__('parameters', new_params)

    def get(self, key, default=None):
        result = super().get(key, default)
        if isinstance(result, SmartValue):
            return result._actual
        return result

    def __getitem__(self, key):
        result = super().__getitem__(key)
        if isinstance(result, SmartValue):
            return result._actual
        return result


class SmartParamDict(dict):
    """Parameters sub-dict that returns SmartValue entries."""

    def __getitem__(self, key):
        return super().__getitem__(key)

    def get(self, key, default=None):
        result = super().get(key, default)
        if result is default and isinstance(default, dict):
            return SmartValue(default, default)
        return result


class SmartValue:
    """
    Value wrapper supporting:
    - .get('value', default)
    - int(), float(), str(), bool() conversion
    - dict subscript and 'in' operator
    - all arithmetic and comparison operators
    """

    def __init__(self, actual_value, original_value=None):
        self._actual = actual_value
        self._original = original_value if original_value is not None else actual_value

    def get(self, key, default=None):
        if key == 'value':
            return self._actual
        if isinstance(self._original, dict):
            return self._original.get(key, default)
        return default

    def __getitem__(self, key):
        if key == 'value':
            return self._actual
        if isinstance(self._original, dict):
            result = self._original.get(key)
            if isinstance(result, dict) and 'value' in result:
                return SmartValue(result['value'], result)
            return result
        raise TypeError(f"'{type(self._actual).__name__}' object is not subscriptable")

    def __contains__(self, key):
        if isinstance(self._original, dict):
            return key in self._original
        return False

    def __int__(self):      return int(self._actual)
    def __float__(self):    return float(self._actual)
    def __str__(self):      return str(self._actual)
    def __bool__(self):     return bool(self._actual)
    def __repr__(self):     return repr(self._actual)

    def __eq__(self, other):  return self._actual == other
    def __lt__(self, other):  return self._actual < other
    def __le__(self, other):  return self._actual <= other
    def __gt__(self, other):  return self._actual > other
    def __ge__(self, other):  return self._actual >= other

    def __add__(self, other):       return self._actual + other
    def __sub__(self, other):       return self._actual - other
    def __mul__(self, other):       return self._actual * other
    def __truediv__(self, other):   return self._actual / other
    def __radd__(self, other):      return other + self._actual
    def __rsub__(self, other):      return other - self._actual
    def __rmul__(self, other):      return other * self._actual
    def __rtruediv__(self, other):  return other / self._actual
