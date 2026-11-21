from pathlib import Path
from unittest.mock import Mock,patch
import tempfile,unittest
from rebirth.jobs import Jobs
from rebirth.control import RunControl
class JobProgress(unittest.TestCase):
 def test_last_phase_and_finished_time_are_based_on_actual_events(self):
  events=[{'kind':'phase_started','actor':'cash','data':{'phase':'review'}},{'kind':'tool_result','actor':'cash','data':{}}]
  store=Mock();store.events.return_value=events
  jobs=Jobs(store,'not-read.json');engine=Mock();engine.run_id='r'
  jobs.entries['j']={'merchant':'m','mode':'simulation','state':'running','engine':engine,'control':RunControl(),'result':None,'started':10}
  with patch('rebirth.jobs.monotonic',return_value=315):
   a=jobs.get('m','j');self.assertEqual(a['elapsed_seconds'],305);self.assertFalse(a['progress']['output_recorded'])
   events.append({'kind':'agent_result','actor':'cash','data':{'phase':'review'}})
   jobs.entries['j'].update(finished=20,state='completed')
   b=jobs.get('m','j');self.assertEqual(b['elapsed_seconds'],10);self.assertTrue(b['progress']['output_recorded'])
  jobs.pool.shutdown()

 def test_one_completed_role_does_not_hide_other_active_role(self):
  store=Mock();store.events.return_value=[{'kind':'phase_started','actor':'inventory','data':{'phase':'review'}},{'kind':'phase_started','actor':'cash','data':{'phase':'review'}},{'kind':'agent_result','actor':'cash','data':{'phase':'review'}}]
  jobs=Jobs(store,'not-read.json');engine=Mock();engine.run_id='r'
  jobs.entries['j']={'merchant':'m','mode':'simulation','state':'running','engine':engine,'control':RunControl(),'result':None,'started':0}
  value=jobs.get('m','j');self.assertEqual(value['progress']['role'],'inventory');self.assertFalse(value['progress']['output_recorded']);jobs.pool.shutdown()
