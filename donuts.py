from __future__ import print_function, division
import numpy as np   
from astropy.io import fits
from scipy.fftpack import fft, ifft
from scipy import ndimage, conjugate, polyfit, polyval

class Donuts(object):
	def __init__(self, refimage, image_ext=0, exposure='EXPTIME',
				 normalise=True, subtract_bkg=True, boarder=64, ntiles=32):
		'''
		Generate a reference image for measuring frame to frame offsets. 
		Assume the following defaults:
			Normalise the image to ADU/s = True
			Edge exclusion boarder = 64 pixels
			N tiles used in the background subtraction = 32

		Look up proper docstrings	
		'''
		self.image_ext = image_ext
		self.boarder = boarder
		self.ntiles = ntiles
		self.normalise = normalise
		self.refimage = refimage
		self.subtract_bkg = subtract_bkg

		h = fits.open(refimage)
		self.texp = float(h[image_ext].header[exposure])
		# get image dimmensions
		self.dy, self.dx = h[image_ext].data.shape

		# check if the CCD is a funny shape. Normal CCDs should divide by 16 with 
		# no remainder. NITES for example does not (1030,1057) instead of (1024,1024)
		numx,rx = divmod(dx, 16)
		numy,ry = divmod(dy, 16)
		if rx != 0 or ry != 0:
			self.dimx = (dx / self.base) * self.base
			self.dimy = (dy / self.base) * self.base
		else:
			self.dimx = dx
			self.dimy = dy

		# get the reference data, with tweaked shape if needed, excluding boarder
		self.ref_data = h[self.image_ext].data[self.boarder:self.dimy - self.boarder, self.boarder:self.dimx - self.boarder]

		# working image size
		self.w_dimy,self.w_dimx = ref_data.shape

		# set up tiles for bkg subtract
		self.tilesizex = self.w_dimx / self.ntiles
		self.tilesizey = self.w_dimy / self.ntiles

		# adjust image if requested
		if self.subtract_bkg:
			self.bkgmap = __generate_bkg_map(self.ref_data, self.ntiles, self.tilesizex, self.tilesizey)
			self.ref_data = self.ref_data - self.bkgmap
		if self.normalise:
			self.ref_data = self.ref_data / self.texp

		self.ref_xproj = np.sum(self.ref_data, axis=0)
		self.ref_yproj = np.sum(self.ref_data, axis=1)

		self.x = np.linspace(0, self.ref_data.shape[1], self.ref_data.shape[1])
		self.y = np.linspace(0, self.ref_data.shape[0], self.ref_data.shape[0])

	def __generate_bkg_map(self,data,tile_num,tilesizex,tilesizey):
		'''
		Create a background map to subtract from each image
		before doing the cross correlation
		'''
		# create coarse map
		coarse = np.empty((tile_num, tile_num))
		for i in range(0, tile_num):
			for j in range(0, tile_num):
				coarse[i][j] = np.median(data[(i * tilesizey):(i + 1) * tilesizey, (j * tilesizex):(j + 1) * tilesizex])
		# resample it out to data size
		bkgmap = ndimage.zoom(coarse, (tilesizey, tilesizex), order=2)
		return bkgmap

	@property
	def print_summary(self):
		'''
		Print a summary of the settings we've chosen
		'''
		print("Data Summary:")
		print("\tWorking on CCD size: {0:d} x {1:d}".format(self.dimx, self.dimy))
		print("\tExcluding boarder of {0:d} pixels".format(self.boarder))
		print("\tCorrections calculated using central: {0:d} x {1:d} pixels".format(self.w_dimx, self.w_dimy))
		if self.subtract_bkg:
			print("Background Subtraction Summary:")
			print("\tUsing {0:d} x {1:d} grid of tiles".format(self.ntiles, self.ntiles))
			print("\tEach {0:d} x {1:d} pixels".format(self.tilesizex, self.tilesizey))

	@property
	def measure_shift(self,checkimage):
		'''
		Generate a check image using the same setup as the reference, then
		measure the shift between each image and the reference
		'''
		self.checkimage = checkimage
		h = fits.open(self.checkimage)
		self.check_data = h[self.image_ext].data[self.boarder:self.dimy - self.boarder, 
							self.boarder:self.dimx - self.boarder]
		
		# adjust image if requested - same as reference
		if self.subtract_bkg:
			self.check_bkgmap = __generate_bkg_map(self.check_data, self.ntiles, self.tilesizex, self.tilesizey)
			self.check_data = self.check_data - self.check_bkgmap
		if self.normalise:
			self.check_data = self.check_data /self.texp
		
		self.check_xproj = np.sum(self.check_data, axis=0)
		self.check_yproj = np.sum(self.check_data, axis=1)

		# FFT of the projection spectra
		F_ref_xproj_n = fft(self.ref_xproj)		
		F_ref_yproj_n = fft(self.ref_yproj)
		F_check_xproj_n = fft(self.check_xproj)
		F_check_yproj_n = fft(self.check_yproj)
				
		# cross correlate in and look for the maximium correlation
		F_ref_xproj_conj_n = conjugate(F_ref_xproj_n)
		F_ref_yproj_conj_n = conjugate(F_ref_yproj_n)
		complex_sum_x_n = F_ref_xproj_conj_n * F_check_xproj_n
		complex_sum_y_n = F_ref_yproj_conj_n * F_check_yproj_n
		Phi_ref_check_m_x_n = ifft(complex_sum_x_n)
		Phi_ref_check_m_y_n = ifft(complex_sum_y_n)
		z_x_n = max(Phi_ref_check_m_x_n)
		z_pos_x_n = np.where(Phi_ref_check_m_x_n == z_x_n)
		z_y_n = max(Phi_ref_check_m_y_n)
		z_pos_y_n = np.where(Phi_ref_check_m_y_n == z_y_n)
			
		# turn the location of the maximum into shift in pixels
		# quadratically interpolate over the 3 pixels surrounding
		# the peak in the CCF. This gives sub pixel resolution.	
		tst_y = np.empty(3)
		tst_x = np.empty(3)
		
		# X
		if z_pos_x_n[0][0] <= len(Phi_ref_check_m_x_n) / 2:
			lra_x=[z_pos_x_n[0][0] - 1, z_pos_x_n[0][0], z_pos_x_n[0][0] + 1]
			tst_x[0] = Phi_ref_check_m_x_n[lra_x[0]].real
			tst_x[1] = Phi_ref_check_m_x_n[lra_x[1]].real
			tst_x[2] = Phi_ref_check_m_x_n[lra_x[2]].real
			coeffs_n_x = polyfit(lra_x, tst_x, 2)
			besty_n_x = polyval(coeffs_n_x, lra_x)
			self.solution_n_x = -(-coeffs_n_x[1] / (2 * coeffs_n_x[0]))
		elif z_pos_x_n[0][0] > len(Phi_ref_check_m_x_n) / 2 and z_pos_x_n[0][0] != len(Phi_ref_check_m_x_n) - 1:
			lra_x=[z_pos_x_n[0][0] - 1, z_pos_x_n[0][0], z_pos_x_n[0][0] + 1]
			tst_x[0] = Phi_ref_check_m_x_n[lra_x[0]].real
			tst_x[1] = Phi_ref_check_m_x_n[lra_x[1]].real
			tst_x[2] = Phi_ref_check_m_x_n[lra_x[2]].real
			coeffs_n_x = polyfit(lra_x, tst_x, 2)
			besty_n_x = polyval(coeffs_n_x, lra_x)
			self.solution_n_x = len(Phi_ref_check_m_x_n) + (coeffs_n_x[1] / (2 * coeffs_n_x[0]))
		elif z_pos_x_n[0][0] == len(Phi_ref_check_m_x_n) - 1:
			lra_x=[-1, 0, 1] 
			tst_x[0] = Phi_ref_check_m_x_n[-2].real
			tst_x[1] = Phi_ref_check_m_x_n[-1].real
			tst_x[2] = Phi_ref_check_m_x_n[0].real
			coeffs_n_x = polyfit(lra_x, tst_x, 2)
			besty_n_x = polyval(coeffs_n_x, lra_x)
			self.solution_n_x = 1 + (coeffs_n_x[1] / (2 * coeffs_n_x[0]))	
		else: #if z_pos_x_n[0][0] == 0:
			lra_x=[1, 0, -1] 
			tst_x[0] = Phi_ref_check_m_x_n[-1].real
			tst_x[1] = Phi_ref_check_m_x_n[0].real
			tst_x[2] = Phi_ref_check_m_x_n[1].real
			coeffs_n_x = polyfit(lra_x, tst_x, 2)
			besty_n_x = polyval(coeffs_n_x, lra_x)
			self.solution_n_x = -coeffs_n_x[1] / (2 * coeffs_n_x[0])		
		print("X: {0:.2f}".format(self.solution_n_x))
		
		# Y 
		if z_pos_y_n[0][0] <= len(Phi_ref_check_m_y_n)/2:
			lra_y=[z_pos_y_n[0][0] - 1, z_pos_y_n[0][0], z_pos_y_n[0][0] + 1]	
			tst_y[0] = Phi_ref_check_m_y_n[lra_y[0]].real
			tst_y[1] = Phi_ref_check_m_y_n[lra_y[1]].real
			tst_y[2] = Phi_ref_check_m_y_n[lra_y[2]].real
			coeffs_n_y = polyfit(lra_y, tst_y, 2)
			besty_n_y = polyval(coeffs_n_y, lra_y)
			self.solution_n_y = -(-coeffs_n_y[1]/(2*coeffs_n_y[0]))
		if z_pos_y_n[0][0] > len(Phi_ref_check_m_y_n) / 2 and z_pos_y_n[0][0] != len(Phi_ref_check_m_y_n) - 1:
			lra_y=[z_pos_y_n[0][0]-1,z_pos_y_n[0][0],z_pos_y_n[0][0]+1]
			tst_y[0] = Phi_ref_check_m_y_n[lra_y[0]].real
			tst_y[1] = Phi_ref_check_m_y_n[lra_y[1]].real
			tst_y[2] = Phi_ref_check_m_y_n[lra_y[2]].real
			coeffs_n_y = polyfit(lra_y, tst_y, 2)
			besty_n_y = polyval(coeffs_n_y, lra_y)
			self.solution_n_y = len(Phi_ref_check_m_y_n) + (coeffs_n_y[1] / (2 * coeffs_n_y[0]))	
		if z_pos_y_n[0][0] == len(Phi_ref_check_m_y_n) - 1:
			lra_y=[-1,0,1] 
			tst_y[0] = Phi_ref_check_m_y_n[-2].real
			tst_y[1] = Phi_ref_check_m_y_n[-1].real
			tst_y[2] = Phi_ref_check_m_y_n[0].real
			coeffs_n_y = polyfit(lra_y, tst_y, 2)
			besty_n_y = polyval(coeffs_n_y, lra_y)
			self.solution_n_y = 1 + (coeffs_n_y[1] / (2 * coeffs_n_y[0]))		
		else: #if z_pos_y_n[0][0] == 0:
			lra_y = [1, 0, -1] 
			tst_y[0] = Phi_ref_check_m_y_n[-1].real
			tst_y[1] = Phi_ref_check_m_y_n[0].real
			tst_y[2] = Phi_ref_check_m_y_n[1].real
			coeffs_n_y = polyfit(lra_y, tst_y, 2)
			besty_n_y = polyval(coeffs_n_y, lra_y)
			self.solution_n_y = -coeffs_n_y[1] / (2 * coeffs_n_y[0])				
		print("Y: {0:.2f}".format(self.solution_n_y))
		return self.solution_n_x,self.solution_n_y

# planned usage
d = Donuts(refimage='filename.fits', image_ext=0, exposure='EXPTIME', 
			normalise=True, subtract_bkg=True, boarder=64, ntiles=32)
d.print_summary()
# assumes all the settings from the ref image generation
x, y = d.measure_shift(checkimage='filename.fits')


