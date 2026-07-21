from tools.analyze_enclosure_cad import (
    choose_section_planes,
    proposed_face_json,
    trapezoid_taper,
)


def test_trapezoid_taper_returns_total_and_symmetric_side_offset() -> None:
    taper = trapezoid_taper(143.36, 145.20)

    assert round(taper.difference, 2) == 1.84
    assert round(taper.side_offset, 2) == 0.92


def test_section_planes_are_offset_toward_the_body_in_either_direction() -> None:
    ascending = choose_section_planes(-35.2, 0.0, 1.2)
    descending = choose_section_planes(35.2, 0.0, 1.2)

    assert ascending.near_closed == -34.0
    assert ascending.near_open == -1.2
    assert descending.near_closed == 34.0
    assert descending.near_open == 1.2


def test_proposed_json_maps_short_and_long_faces_consistently() -> None:
    fragment = proposed_face_json(
        top_length=143.356,
        bottom_length=145.200,
        top_width=119.356,
        bottom_width=121.200,
        body_height=35.200,
    )

    assert fragment == {
        "faces": {
            "B": {
                "shape": "trapezoid",
                "top_width": 119.36,
                "bottom_width": 121.2,
                "height": 35.2,
            },
            "C": {
                "shape": "trapezoid",
                "top_width": 143.36,
                "bottom_width": 145.2,
                "height": 35.2,
            },
            "D": {
                "shape": "trapezoid",
                "top_width": 119.36,
                "bottom_width": 121.2,
                "height": 35.2,
            },
            "E": {
                "shape": "trapezoid",
                "top_width": 143.36,
                "bottom_width": 145.2,
                "height": 35.2,
            },
        }
    }
