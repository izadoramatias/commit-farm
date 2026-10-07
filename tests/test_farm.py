import copy
from datetime import date
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('farm', Path(__file__).resolve().parents[1] / 'scripts/generate.py')
farm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(farm)


class FarmTests(unittest.TestCase):
    def test_year_rollover_leap_year_and_week_layout(self):
        for end in [date(2024, 2, 29), date(2026, 1, 1), date(2026, 10, 7), date(2026, 10, 10)]:
            days = farm.normalize(farm.demo_calendar(end), end)
            self.assertEqual(len(days), 365)
            self.assertEqual(days[-1]['date'], end.isoformat())
            self.assertEqual(days[0]['date'], farm.bounds(end)[0].isoformat())
            self.assertEqual(len({d['date'] for d in days}), 365)
            svg = ET.fromstring(farm.render(days, 'demo', 'Horta', end, True))
            rendered = svg.findall('.//{http://www.w3.org/2000/svg}g[@data-date]')
            self.assertEqual(len(rendered), 365)
            self.assertEqual({int(e.get('data-level')) for e in rendered}, set(range(5)))

    def test_empty_activity_is_valid(self):
        end = date(2026, 10, 7)
        data = farm.demo_calendar(end)
        for day in data['weeks'][0]['contributionDays']:
            day.update(contributionCount=0, contributionLevel='NONE')
        days = farm.normalize(data, end)
        self.assertTrue(all(d['level'] == 0 for d in days))

    def test_reject_missing_duplicate_invalid_days(self):
        end = date(2026, 10, 7)
        for mode in ['missing', 'duplicate', 'weekday', 'level', 'negative']:
            data = copy.deepcopy(farm.demo_calendar(end))
            days = data['weeks'][0]['contributionDays']
            if mode == 'missing': days.pop()
            if mode == 'duplicate': days.append(days[0])
            if mode == 'weekday': days[0]['weekday'] = 9
            if mode == 'level': days[0]['contributionLevel'] = 'UNEXPECTED'
            if mode == 'negative': days[0]['contributionCount'] = -1
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                farm.normalize(data, end)

    def test_graphql_request_and_response(self):
        end = date(2026, 10, 7)
        expected = farm.demo_calendar(end)
        response = {'data': {'user': {'contributionsCollection': {'contributionCalendar': expected}}}}
        with patch.object(farm, 'urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as mock:
            actual = farm.fetch_calendar('octocat', 'fake-test-token', end)
        self.assertEqual(actual, expected)
        request = mock.call_args.args[0]
        variables = json.loads(request.data)['variables']
        self.assertEqual(variables['login'], 'octocat')
        self.assertEqual(variables['from'], '2025-10-08T00:00:00Z')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fake-test-token')

    def test_api_error_preserves_previous_svg(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'farm.svg'
            output.write_text('previous image')
            with patch.dict(os.environ, {'FARM_USERNAME': 'octocat', 'GH_TOKEN': 'fake-test-token'}):
                with patch.object(farm, 'urlopen', return_value=io.BytesIO(b'{"errors":[{"message":"denied"}]}')):
                    with self.assertRaises(ValueError):
                        farm.main(['--output', str(output)])
            self.assertEqual(output.read_text(), 'previous image')

    def test_escaping_and_repeatability(self):
        end = date(2026, 10, 7)
        days = farm.normalize(farm.demo_calendar(end), end)
        one = farm.render(days, 'demo', '<script>&', end, True)
        self.assertEqual(one, farm.render(days, 'demo', '<script>&', end, True))
        self.assertNotIn('<script>', one)
        ET.fromstring(one)


if __name__ == '__main__':
    unittest.main()
