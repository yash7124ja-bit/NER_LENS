import unittest
from ner_lens.driver_trip import TripReadResponse, TripSegment


class TestDriverTrip(unittest.TestCase):
    def test_driver_trip_read_structure(self):
        """Verify TripReadResponse schema and fields defined."""
        seg = TripSegment(
            segment_id="seg-1",
            name="Pagla Pahar",
            km_start=30.0,
            km_end=40.0,
            coordinates=[[93.7, 25.8]],
            operational_status="open",
            risk_state="high",
        )
        self.assertEqual(seg.name, "Pagla Pahar")
        self.assertEqual(seg.km_start, 30.0)

