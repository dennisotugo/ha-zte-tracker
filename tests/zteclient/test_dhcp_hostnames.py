"""F8648P hostname and login compatibility, without a live router."""
from unittest import TestCase
from unittest.mock import Mock, patch
import sys
import requests
from test_router_details_parsing import _load_client

XML = '''<ajax_response_xml_root><IF_ERRORSTR>SUCC</IF_ERRORSTR>
<OBJ_DHCPHOSTINFO_ID><Instance>
<ParaName>MACAddr</ParaName><ParaValue>aa:bb:cc:dd:ee:ff</ParaValue>
<ParaName>IPAddr</ParaName><ParaValue>192.0.2.10</ParaValue>
<ParaName>HostName</ParaName><ParaValue>Test-Phone</ParaValue>
</Instance></OBJ_DHCPHOSTINFO_ID></ajax_response_xml_root>'''


class TestDhcpHostnames(TestCase):
    def setUp(self):
        self.client = _load_client()('router.invalid', 'user', 'test', 'F6640')
        self.session = self.client.session = Mock()
        self.session.get.return_value = Mock(text=XML)
        self.client.get_lan_devices = Mock(return_value=[{
            'MACAddress': 'AA:BB:CC:DD:EE:FF',
            'IPAddress': '192.0.2.10', 'HostName': '',
        }])
        self.client.get_wifi_devices = Mock(return_value=[])

    def test_blank_name_is_filled_from_router_xml(self):
        self.assertEqual(self.client.get_devices_response()[0]['HostName'], 'Test-Phone')
        urls = [c.args[0] for c in self.session.get.call_args_list]
        self.assertIn('_type=menuView&_tag=lanMgrIpv4', urls[0])
        self.assertIn('Localnet_LanMgrIpv4_DHCPHostInfo_lua.lua', urls[1])

    def test_existing_name_is_preserved_without_extra_requests(self):
        self.client.get_lan_devices.return_value[0]['HostName'] = 'Existing'
        self.assertEqual(self.client.get_devices_response()[0]['HostName'], 'Existing')
        self.session.get.assert_not_called()

    def test_stale_lease_address_cannot_name_another_client(self):
        self.client.get_lan_devices.return_value[0]['IPAddress'] = '192.0.2.11'
        self.assertEqual(self.client.get_devices_response()[0]['HostName'], '')

    def test_wrong_mac_cannot_name_another_client(self):
        self.client.get_lan_devices.return_value[0]['MACAddress'] = '00:11:22:33:44:55'
        self.assertEqual(self.client.get_devices_response()[0]['HostName'], '')

    def test_invalid_xml_does_not_drop_devices(self):
        self.session.get.return_value.text = '<invalid'
        self.assertEqual(len(self.client.get_devices_response()), 1)

    def test_dhcp_timeout_does_not_drop_devices(self):
        self.session.get.side_effect = requests.Timeout('test timeout')
        self.assertEqual(len(self.client.get_devices_response()), 1)

    def test_router_error_cannot_assign_names(self):
        self.session.get.return_value.text = XML.replace('SUCC', 'SessionTimeout')
        self.assertEqual(self.client.get_devices_response()[0]['HostName'], '')

    def test_other_profiles_do_not_query_dhcp(self):
        self.client.paths = dict(self.client.paths, dhcp_hostnames=False)
        self.assertEqual(self.client.get_devices_response()[0]['HostName'], '')
        self.session.get.assert_not_called()

    def test_login_refreshes_cookies_without_mesh_queries(self):
        self.assertFalse(self.client.mesh_topology)
        module = sys.modules[self.client.__class__.__module__]
        self.client.get_session_token = Mock(return_value='test-session')
        self.client.log_request = Mock()
        self.session.get.return_value.content = b'<ajax_response_xml_root>test-token</ajax_response_xml_root>'
        self.session.post.return_value.json.return_value = {'login_need_refresh': 1}
        with patch.object(module, 'Session', return_value=self.session):
            self.assertTrue(self.client.login())
        urls = [call.args[0] for call in self.session.get.call_args_list]
        self.assertEqual(urls[0], self.client.base_url + '/')
        self.assertEqual(urls[-1], self.client.base_url + '/')
        self.assertEqual(len(urls), 3)
