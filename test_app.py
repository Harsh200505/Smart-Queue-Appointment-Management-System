import unittest
import app as queue_app

class QueueAppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.client = queue_app.app.test_client()

    def test_home(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'SmartQueue', r.data)

    def test_book_page(self):
        r = self.client.get('/book')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Book an Appointment', r.data)

    def test_queue_api(self):
        r = self.client.get('/api/queue')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.is_json)

if __name__ == '__main__':
    unittest.main()
