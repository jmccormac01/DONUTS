"""Real world test of Donuts using real images from NITES
"""
import os.path
import numpy as np
from ..donuts import Donuts

ROOT_PATH = os.path.dirname(__file__)
DATA_DIR = os.path.join(ROOT_PATH, '..', 'data')

# Test the donuts code using real data
def test_full_integration2():
    """Test real world usage of Donuts with real data
    
    Parameters
    ----------
    None

    Returns
    -------
    None

    Raises
    ------
    None
    """
    test_ref_image = os.path.join(DATA_DIR, 'J17490840-001.fit')
    d = Donuts(refimage=test_ref_image, image_ext=0, exposure='EXPTIME',
               normalise=True, subtract_bkg=True, prescan_width=0,
               overscan_width=0, boarder=64, ntiles=28)
    # print a summary of the setup
    d.print_summary()
    # assumes all the settings from the ref image generation
    # and calculates the shift between the images
    imlist = ['J17490840-001.fit',
              'J17490840-002.fit',
              'J17490840-003.fit']
    x_expected = [0.00, -0.73, -2.25]
    y_expected = [0.00, 2.29, 2.62]
    for image, x_ex, y_ex in zip(imlist, x_expected, y_expected):
        test_check_image = os.path.join(DATA_DIR, image)
        x, y = d.measure_shift(checkimage=test_check_image)
        assert np.isclose(x, x_ex, rtol=0.1, atol=0.1)
        assert np.isclose(y, y_ex, rtol=0.1, atol=0.1)