"""Representative vendor frames; no network requests or real credentials."""
import json
import unittest
from rebirth.managed_ws import invoke,connection_error
from rebirth.control import RunControl, LimitExceeded
from rebirth.providers import ProviderError

ACK={'type':'event','event':'connection.ack'}
ACTION={'action':'final','result':{'notes':['verified']}}


class Socket:
    def __init__(self,frames):self.frames=iter(frames);self.sent=[];self.closed=False
    def recv(self,timeout):return json.dumps(next(self.frames))
    def send(self,value):self.sent.append(json.loads(value))
    def close(self):self.closed=True


class ManagedTest(unittest.TestCase):
    def test_observed_gateway_nested_deltas_and_empty_final_content(self):
        text=json.dumps(ACTION)
        frames=[{'response_kind':'e2a.chunk','status':'in_progress','body':{
            'event_type':'chat.delta','delta':{'event_type':'chat.delta','content':part,'stream_source_id':'main'}}}
            for part in [text[:14],text[14:]]]
        frames.append({'response_kind':'e2a.chunk','status':'in_progress','is_final':False,
            'body':{'event_type':'chat.final','delta':{'event_type':'chat.final','content':'','stream_source_id':'main'}}})
        self.assertEqual(self.call(frames),ACTION)

    def test_current_gateway_final_chunk_uses_body_delta(self):
        self.assertEqual(self.call([{'response_kind':'e2a.chunk','status':'in_progress',
            'body':{'event_type':'chat.final','delta_kind':'text','delta':json.dumps(ACTION)}}]),ACTION)

    def test_empty_terminal_chunk_finishes_accumulated_text(self):
        self.assertEqual(self.call([
            {'response_kind':'e2a.chunk','body':{'event_type':'chat.delta','delta':json.dumps(ACTION)}},
            {'response_kind':'e2a.chunk','body':{'event_type':'chat.final','delta':''}}]),ACTION)

    def test_large_platform_metadata_does_not_exhaust_model_text_budget(self):
        frames=[{'response_kind':'e2a.chunk','body':{'event_type':'runtime.status','metadata':'x'*50000}} for _ in range(4)]
        frames.append({'response_kind':'e2a.complete','status':'succeeded','is_final':True,
            'body':{'result':{'content':json.dumps(ACTION)}}})
        control=RunControl(max_output_bytes=200)
        self.assertEqual(self.call(frames,control),ACTION)
        self.assertEqual(control.output_bytes,len(json.dumps(ACTION).encode()))

    def test_final_repeat_of_stream_is_not_counted_twice(self):
        text=json.dumps(ACTION);control=RunControl(max_output_bytes=len(text.encode()))
        frames=[{'response_kind':'e2a.chunk','body':{'event_type':'chat.delta','delta':text}},
            {'response_kind':'e2a.complete','is_final':True,'status':'succeeded','body':{'result':{'content':text}}}]
        self.assertEqual(self.call(frames,control),ACTION)
        self.assertEqual(control.output_bytes,len(text.encode()))

    def test_final_only_response_still_respects_text_limit(self):
        with self.assertRaises(LimitExceeded):
            self.call([{'response_kind':'e2a.complete','is_final':True,'status':'succeeded',
                'body':{'result':{'content':json.dumps(ACTION)}}}],RunControl(max_output_bytes=5))
        self.assertTrue(self.socket.closed)

    def test_protocol_metadata_still_has_separate_wire_limit(self):
        with self.assertRaisesRegex(ProviderError,'8MB'):
            self.call([{'response_kind':'e2a.chunk','body':{'event_type':'runtime.status','metadata':'x'*900000}} for _ in range(10)])
        self.assertTrue(self.socket.closed)

    def test_diagnostic_status_without_secret_exception_text(self):
        class Response:status_code=401
        error=RuntimeError('secret-must-not-appear');error.response=Response()
        result=connection_error(error)
        self.assertIn('HTTP 401',result)
        self.assertNotIn('secret-must-not-appear',result)

    def test_timeout_does_not_blame_credentials(self):
        result=connection_error(TimeoutError('sensitive network detail'))
        self.assertIn('超时',result)
        self.assertIn('不能据此判断',result)
        self.assertNotIn('sensitive',result)

    def call(self,frames,control=None):
        self.socket=Socket([ACK]+frames);self.connection={}
        def connector(url,**kwargs):self.connection.update(url=url,**kwargs);return self.socket
        return invoke('wss://example.invalid/runtimes/managed-test/ws','fake-secret','run-cash-1',
            {'context':{'role':'cash'}},control or RunControl(),connector=connector)

    def test_final_authoritative_without_duplicate_streamed_text(self):
        result=self.call([{'response_kind':'e2a.chunk','body':{'event_type':'chat.delta','delta':'discard draft'}},
            {'response_kind':'e2a.complete','status':'succeeded','is_final':True,'body':{'result':{'content':json.dumps(ACTION)}}}])
        self.assertEqual(result,ACTION);self.assertTrue(self.socket.closed)
        request=self.socket.sent[0]
        self.assertEqual(request['req_method'],'chat.send')
        self.assertEqual(json.loads(request['params']['query'])['context']['role'],'cash')
        self.assertNotIn('fake-secret',json.dumps(request))
        self.assertEqual(self.connection['additional_headers']['Authorization'],'Bearer fake-secret')
        self.assertEqual(self.connection['origin'],'https://example.invalid')

    def test_permission_is_not_automatically_granted(self):
        with self.assertRaisesRegex(ProviderError,'未自动授权'):
            self.call([{'tag':'TOOL_PERMISSION','decision':'ASK'}])
        self.assertEqual(len(self.socket.sent),1);self.assertTrue(self.socket.closed)

    def test_question_is_not_automatically_answered(self):
        with self.assertRaisesRegex(ProviderError,'未代选答案'):
            self.call([{'payload':{'event_type':'chat.ask_user_question'}}])
        self.assertEqual(len(self.socket.sent),1)

    def test_error_does_not_accept_earlier_valid_draft(self):
        with self.assertRaises(ProviderError):
            self.call([{'response_kind':'e2a.chunk','body':{'event_type':'chat.delta','delta':json.dumps(ACTION)}},
                {'response_kind':'e2a.error','body':{'message':'sensitive message'}}])

    def test_budget_failure_propagates_and_closes_connection(self):
        with self.assertRaises(LimitExceeded):
            self.call([{'response_kind':'e2a.chunk','body':{'delta':'x'*400}}],RunControl(max_output_bytes=200))
        self.assertTrue(self.socket.closed)

    def test_plaintext_connection_rejected_without_connecting(self):
        def forbidden(*a,**k):self.fail('must not connect')
        with self.assertRaises(ProviderError):
            invoke('ws://example.invalid/ws','fake','session',{},RunControl(),connector=forbidden)


if __name__=='__main__':unittest.main()
