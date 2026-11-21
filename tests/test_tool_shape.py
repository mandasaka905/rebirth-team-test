import unittest
from rebirth.tool_shape import normalize
from rebirth.tool_batch import expand
from rebirth.domain import ValidationError
class ToolShapeTests(unittest.TestCase):
    def test_advertised_fixed_limit_is_metadata_not_a_relaxed_server_bound(self):
        calls=[{'name':'inventory_analyze','arguments':{}}]
        a={'name':'read_tools','arguments':{'calls':calls,'limit':8}}
        c,changed=normalize(a);self.assertTrue(changed);self.assertEqual(expand(c['name'],c['arguments']),[('inventory_analyze',{})])
        for value in (9,0,True,'8'):
            with self.assertRaises(ValidationError):normalize({'name':'read_tools','arguments':{'calls':calls,'limit':value}})
        with self.assertRaises(ValidationError):
            c,_=normalize({'name':'read_tools','arguments':{'calls':calls*9,'limit':8}});expand(c['name'],c['arguments'])
    def test_explicit_aliases_preserve_arguments(self):
        a={'action':'tool','name':'read_tools','parameters':{'tools':[{'tool':'inventory_analyze','params':{}}]}}
        c,changed=normalize(a);self.assertTrue(changed);self.assertEqual(expand(c['name'],c['arguments']),[('inventory_analyze',{})]);self.assertIn('parameters',a)
    def test_missing_ambiguous_and_unregistered_still_rejected(self):
        for a in [{'action':'tool','name':'read_tools','arguments':{'calls':[{'name':'inventory_analyze'}]}},
                  {'action':'tool','name':'read_tools','calls':[{'name':'http://bad','arguments':{}}]},
                  {'action':'tool','name':'read_tools','arguments':{},'parameters':{}}]:
            with self.assertRaises(ValidationError):
                c,_=normalize(a);expand(c['name'],c.get('arguments',{}))
