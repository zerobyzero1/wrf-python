import unittest as ut
import numpy.testing as nt 
import numpy as np
import numpy.ma as ma
import os, sys
import subprocess

from wrf import (getvar, interplevel, interpline, vertcross, vinterp,
                 disable_xarray, xarray_enabled, to_np,
                 xy_to_ll, ll_to_xy, xy_to_ll_proj, ll_to_xy_proj,
                 extract_global_attrs, viewitems, CoordPair)
from wrf.util import is_multi_file

NCL_EXE = "/Users/ladwig/nclbuild/6.3.0/bin/ncl"
TEST_FILE = "/Users/ladwig/Documents/wrf_files/wrfout_d01_2010-06-13_21:00:00"
OUT_NC_FILE = "/tmp/wrftest.nc"

# Python 3
if sys.version_info > (3,):
    xrange = range

def setUpModule():
    ncarg_root = os.environ.get("NCARG_ROOT", None)
    if ncarg_root is None:
        raise RuntimeError("$NCARG_ROOT environment variable not set")
        
    
    this_path = os.path.realpath(__file__)
    ncl_script = os.path.join(os.path.dirname(this_path),
                              "ncl_get_var.ncl")
    ncfile = TEST_FILE + ".nc" # NCL requires extension
    
    # This needs to be set when PyNIO is installed, since PyNIOs data does
    # not contain the dat file for the CAPE calcluations
    os.environ["NCARG_NCARG"] = os.path.join(os.environ["NCARG_ROOT"],
                                             "lib", "ncarg")
    cmd = "%s %s 'in_file=\"%s\"' 'out_file=\"%s\"'" % (NCL_EXE,
                                                        ncl_script,
                                                        ncfile,
                                                        OUT_NC_FILE)
    
    #print cmd
    
    if not os.path.exists(OUT_NC_FILE):
        status = subprocess.call(cmd, shell=True)
        if (status != 0):
            raise RuntimeError("NCL script failed.  Could not set up test.")

# Using helpful information at: 
# http://eli.thegreenplace.net/2014/04/02/dynamically-generating-python-test-cases
def make_test(varname, wrf_in, referent, multi=False, repeat=3, pynio=False):
    def test(self):

        try:
            from netCDF4 import Dataset as NetCDF
        except:
            pass
        
        try:
            from PyNIO import Nio
        except:
            pass
        
        if not multi:
            timeidx = 0
            if not pynio:
                in_wrfnc = NetCDF(wrf_in)
            else:
                # Note: Python doesn't like it if you reassign an outer scoped
                # variable (wrf_in in this case)
                if not wrf_in.endswith(".nc"):
                    wrf_file = wrf_in + ".nc"
                else:
                    wrf_file = wrf_in
                in_wrfnc = Nio.open_file(wrf_file)
        else:
            timeidx = None
            if not pynio:
                nc = NetCDF(wrf_in)
                in_wrfnc = [nc for i in xrange(repeat)]
            else:
                if not wrf_in.endswith(".nc"):
                    wrf_file = wrf_in + ".nc"
                else:
                    wrf_file = wrf_in
                nc = Nio.open_file(wrf_file)
                in_wrfnc = [nc for i in xrange(repeat)]
            
        
        refnc = NetCDF(referent)
        
        # These have a left index that defines the product type
        multiproduct = varname in ("uvmet", "uvmet10", "cape_2d", "cape_3d", 
                                   "cfrac")
        
        
        if not multi:
            ref_vals = refnc.variables[varname][:]
        else:
            data = refnc.variables[varname][:]
            if (varname != "uvmet" and varname != "uvmet10" 
                and varname != "cape_2d" and varname != "cape_3d"):
                new_dims = [repeat] + [x for x in data.shape]
            elif (varname == "uvmet" or varname == "uvmet10" 
                  or varname == "cape_3d"):
                new_dims = [2] + [repeat] + [x for x in data.shape[1:]]
            elif (varname == "cape_2d"):
                new_dims = [4] + [repeat] + [x for x in data.shape[1:]]
            elif (varname == "cfrac"):
                new_dims = [3] + [repeat] + [x for x in data.shape[1:]]

                
            masked=False
            if (isinstance(data, ma.core.MaskedArray)):
                masked=True
            
            if not masked:
                ref_vals = np.zeros(new_dims, data.dtype)
            else:
                ref_vals = ma.asarray(np.zeros(new_dims, data.dtype))
            
            for i in xrange(repeat):
                if not multiproduct:
                    ref_vals[i,:] = data[:]
                
                    if masked:
                        ref_vals.mask[i,:] = data.mask[:]
                        
                else:
                    for prod in xrange(ref_vals.shape[0]):
                        ref_vals[prod,i,:] = data[prod,:]
                        
                        if masked:
                            ref_vals.mask[prod,i,:] = data.mask[prod,:]
        
        if (varname == "tc"):
            my_vals = getvar(in_wrfnc, "temp", timeidx=timeidx, units="c")
            tol = 1/100.
            atol = .1 # Note:  NCL uses 273.16 as conversion for some reason
            nt.assert_allclose(to_np(my_vals), ref_vals, tol, atol)
        elif (varname == "pw"):
            my_vals = getvar(in_wrfnc, "pw", timeidx=timeidx)
            tol = .5/100.0
            atol = 0 # NCL uses different constants and doesn't use same
                     # handrolled virtual temp in method
            try:
                nt.assert_allclose(to_np(my_vals), ref_vals, tol, atol)
            except AssertionError:
                print (np.amax(np.abs(to_np(my_vals) - ref_vals)))
                raise
        elif (varname == "cape_2d"):
            cape_2d = getvar(in_wrfnc, varname, timeidx=timeidx)
            tol = 0/100.
            atol = 200.0
            # Let's only compare CAPE values until the F90 changes are 
            # merged back in to NCL.  The modifications to the R and CP
            # changes TK enough that non-lifting parcels could lift, thus
            # causing wildly different values in LCL
            nt.assert_allclose(to_np(cape_2d[0,:]), ref_vals[0,:], tol, atol)
        elif (varname == "cape_3d"):
            cape_3d = getvar(in_wrfnc, varname, timeidx=timeidx)
            # Changing the R and CP constants, while keeping TK within
            # 2%, can lead to some big changes in CAPE.  Tolerances 
            # have been set wide when comparing the with the original
            # NCL.  Change back when the F90 code is merged back with 
            # NCL
            tol = 0/100.
            atol = 200.0
            
            #print np.amax(np.abs(to_np(cape_3d[0,:]) - ref_vals[0,:]))
            nt.assert_allclose(to_np(cape_3d), ref_vals, tol, atol)
        else:
            my_vals = getvar(in_wrfnc, varname, timeidx=timeidx)
            tol = 2/100.
            atol = 0.1
            #print (np.amax(np.abs(to_np(my_vals) - ref_vals)))
            try:
                nt.assert_allclose(to_np(my_vals), ref_vals, tol, atol)
            except:
                print (np.amax(np.abs(to_np(my_vals) - ref_vals)))
                raise
    
    
    return test

def _get_refvals(referent, varname, repeat, multi):
    try:
        from netCDF4 import Dataset as NetCDF
    except:
        pass
        
    refnc = NetCDF(referent)
    
    if not multi:
        ref_vals = refnc.variables[varname][:]
    else:
        data = refnc.variables[varname][:]
        new_dims = [repeat] + [x for x in data.shape]
        masked=False
        if (isinstance(data, ma.core.MaskedArray)):
            masked=True
          
        if not masked:
            ref_vals = np.zeros(new_dims, data.dtype)
        else:
            ref_vals = ma.asarray(np.zeros(new_dims, data.dtype))
              
        for i in xrange(repeat):
            ref_vals[i,:] = data[:]
              
            if masked:
                ref_vals.mask[i,:] = data.mask[:]
                
    return ref_vals

def make_interp_test(varname, wrf_in, referent, multi=False, 
                     repeat=3, pynio=False):
    def test(self):
        try:
            from netCDF4 import Dataset as NetCDF
        except:
            pass
        
        try:
            from PyNIO import Nio
        except:
            pass
        
        if not multi:
            timeidx = 0
            if not pynio:
                in_wrfnc = NetCDF(wrf_in)
            else:
                # Note: Python doesn't like it if you reassign an outer scoped
                # variable (wrf_in in this case)
                if not wrf_in.endswith(".nc"):
                    wrf_file = wrf_in + ".nc"
                else:
                    wrf_file = wrf_in
                in_wrfnc = Nio.open_file(wrf_file)
        else:
            timeidx = None
            if not pynio:
                nc = NetCDF(wrf_in)
                in_wrfnc = [nc for i in xrange(repeat)]
            else:
                if not wrf_in.endswith(".nc"):
                    wrf_file = wrf_in + ".nc"
                else:
                    wrf_file = wrf_in
                nc = Nio.open_file(wrf_file)
                in_wrfnc = [nc for i in xrange(repeat)]
        
        if (varname == "interplevel"):
            ref_ht_500 = _get_refvals(referent, "z_500", repeat, multi)
            hts = getvar(in_wrfnc, "z", timeidx=timeidx)
            p = getvar(in_wrfnc, "pressure", timeidx=timeidx)
            hts_500 = interplevel(hts, p, 500)
            
            nt.assert_allclose(to_np(hts_500), ref_ht_500)
            
        elif (varname == "vertcross"):
            ref_ht_cross = _get_refvals(referent, "ht_cross", repeat, multi)
            ref_p_cross = _get_refvals(referent, "p_cross", repeat, multi)
            
            hts = getvar(in_wrfnc, "z", timeidx=timeidx)
            p = getvar(in_wrfnc, "pressure", timeidx=timeidx)
            
            pivot_point = CoordPair(hts.shape[-1] / 2, hts.shape[-2] / 2) 
            ht_cross = vertcross(hts, p, pivot_point=pivot_point, angle=90.)
            
            # Note:  Until the bug is fixed in NCL, the wrf-python cross 
            # sections will contain one extra point
            nt.assert_allclose(to_np(ht_cross)[...,0:-1], ref_ht_cross, rtol=.01)
            
            # Test opposite
            p_cross1 = vertcross(p,hts,pivot_point=pivot_point, angle=90.0)
            
            nt.assert_allclose(to_np(p_cross1)[...,0:-1], 
                               ref_p_cross, 
                               rtol=.01)
            # Test point to point
            start_point = CoordPair(0, hts.shape[-2]/2)
            end_point = CoordPair(-1,hts.shape[-2]/2)
          
             
            p_cross2 = vertcross(p,hts,start_point=start_point, 
                                end_point=end_point)
            
            nt.assert_allclose(to_np(p_cross1), 
                               to_np(p_cross2))
              
        elif (varname == "interpline"):
            
            ref_t2_line = _get_refvals(referent, "t2_line", repeat, multi)
            
            t2 = getvar(in_wrfnc, "T2", timeidx=timeidx)
            pivot_point = CoordPair(t2.shape[-1] / 2, t2.shape[-2] / 2)
            
            t2_line1 = interpline(t2, pivot_point=pivot_point, angle=90.0)
            
            # Note:  After NCL is fixed, remove the slice.
            nt.assert_allclose(to_np(t2_line1)[...,0:-1], ref_t2_line)
            
            # Test point to point
            start_point = CoordPair(0, t2.shape[-2]/2)
            end_point = CoordPair(-1, t2.shape[-2]/2)
            
            t2_line2 = interpline(t2, start_point=start_point, 
                                  end_point=end_point)
            
            nt.assert_allclose(to_np(t2_line1), to_np(t2_line2))
        elif (varname == "vinterp"):
            # Tk to theta
            fld_tk_theta = _get_refvals(referent, "fld_tk_theta", repeat, multi)
            fld_tk_theta = np.squeeze(fld_tk_theta)
            
            tk = getvar(in_wrfnc, "temp", timeidx=timeidx, units="k")
            
            interp_levels = [200,300,500,1000]
            
            field = vinterp(in_wrfnc, 
                            field=tk, 
                            vert_coord="theta", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="tk",
                            timeidx=timeidx, 
                            log_p=True)
            
            tol = 5/100.
            atol = 0.0001
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_tk_theta)))
            nt.assert_allclose(to_np(field), fld_tk_theta, tol, atol)
            
            # Tk to theta-e
            fld_tk_theta_e = _get_refvals(referent, "fld_tk_theta_e", repeat, multi)
            fld_tk_theta_e = np.squeeze(fld_tk_theta_e)
            
            interp_levels = [200,300,500,1000]
            
            field = vinterp(in_wrfnc, 
                            field=tk, 
                            vert_coord="theta-e", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="tk", 
                            timeidx=timeidx, 
                            log_p=True)
            
            tol = 3/100.
            atol = 50.0001
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_tk_theta_e)/fld_tk_theta_e)*100)
            nt.assert_allclose(to_np(field), fld_tk_theta_e, tol, atol)
            
            # Tk to pressure
            fld_tk_pres = _get_refvals(referent, "fld_tk_pres", repeat, multi)
            fld_tk_pres = np.squeeze(fld_tk_pres)
            
            interp_levels = [850,500]
            
            field = vinterp(in_wrfnc, 
                            field=tk, 
                            vert_coord="pressure", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="tk",
                            timeidx=timeidx,  
                            log_p=True)
            
            field = np.squeeze(field)
            
            #print (np.amax(np.abs(to_np(field) - fld_tk_pres)))
            nt.assert_allclose(to_np(field), fld_tk_pres, tol, atol)
            
            # Tk to geoht_msl
            fld_tk_ght_msl = _get_refvals(referent, "fld_tk_ght_msl", repeat, multi)
            fld_tk_ght_msl = np.squeeze(fld_tk_ght_msl)
            interp_levels = [1,2]
            
            field = vinterp(in_wrfnc, 
                            field=tk, 
                            vert_coord="ght_msl", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="tk",
                            timeidx=timeidx,  
                            log_p=True)
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_tk_ght_msl)))
            nt.assert_allclose(to_np(field), fld_tk_ght_msl, tol, atol)
            
            # Tk to geoht_agl
            fld_tk_ght_agl = _get_refvals(referent, "fld_tk_ght_agl", repeat, multi)
            fld_tk_ght_agl = np.squeeze(fld_tk_ght_agl)
            interp_levels = [1,2]
            
            field = vinterp(in_wrfnc, 
                            field=tk, 
                            vert_coord="ght_agl", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="tk", 
                            timeidx=timeidx, 
                            log_p=True)
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_tk_ght_agl)))
            nt.assert_allclose(to_np(field), fld_tk_ght_agl, tol, atol)
            
            # Hgt to pressure
            fld_ht_pres = _get_refvals(referent, "fld_ht_pres", repeat, multi)
            fld_ht_pres = np.squeeze(fld_ht_pres)
            
            z = getvar(in_wrfnc, "height", timeidx=timeidx, units="m")
            interp_levels = [500,50]
            field = vinterp(in_wrfnc, 
                            field=z, 
                            vert_coord="pressure", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="ght", 
                            timeidx=timeidx, 
                            log_p=True)
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_ht_pres)))
            nt.assert_allclose(to_np(field), fld_ht_pres, tol, atol)
            
            # Pressure to theta
            fld_pres_theta = _get_refvals(referent, "fld_pres_theta", repeat, multi)
            fld_pres_theta = np.squeeze(fld_pres_theta)
            
            p = getvar(in_wrfnc, "pressure", timeidx=timeidx)
            interp_levels = [200,300,500,1000]
            field = vinterp(in_wrfnc, 
                            field=p, 
                            vert_coord="theta", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="pressure", 
                            timeidx=timeidx, 
                            log_p=True)
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_pres_theta)))
            nt.assert_allclose(to_np(field), fld_pres_theta, tol, atol)
            
            # Theta-e to pres
            fld_thetae_pres = _get_refvals(referent, "fld_thetae_pres", repeat, multi)
            fld_thetae_pres = np.squeeze(fld_thetae_pres)
            
            eth = getvar(in_wrfnc, "eth", timeidx=timeidx)
            interp_levels = [850,500,5]
            field = vinterp(in_wrfnc, 
                            field=eth, 
                            vert_coord="pressure", 
                            interp_levels=interp_levels, 
                            extrapolate=True, 
                            field_type="theta-e", 
                            timeidx=timeidx, 
                            log_p=True)
            
            field = np.squeeze(field)
            #print (np.amax(np.abs(to_np(field) - fld_thetae_pres)))
            nt.assert_allclose(to_np(field), fld_thetae_pres, tol, atol)
    
    return test

def extract_proj_params(wrfnc):
    attrs = extract_global_attrs(wrfnc, ("MAP_PROJ", "TRUELAT1", "TRUELAT2",
                                         "STAND_LON", "POLE_LAT", "POLE_LON", 
                                         "DX", "DY"))
    
    result = {key.lower(): val for key,val in viewitems(attrs)}
    
    if is_multi_file(wrfnc):
        wrfnc = wrfnc[0]
    
    result["known_x"] = 0
    result["known_y"] = 0
    result["ref_lat"] = wrfnc.variables["XLAT"][0,0,0]
    result["ref_lon"] = wrfnc.variables["XLONG"][0,0,0]
    
    return result

def make_latlon_test(testid, wrf_in, referent, single, multi=False, repeat=3, 
                     pynio=False):
    def test(self):
        try:
            from netCDF4 import Dataset as NetCDF
        except:
            pass
        
        try:
            from PyNIO import Nio
        except:
            pass
        
        if not multi:
            timeidx = 0
            if not pynio:
                in_wrfnc = NetCDF(wrf_in)
            else:
                # Note: Python doesn't like it if you reassign an outer scoped
                # variable (wrf_in in this case)
                if not wrf_in.endswith(".nc"):
                    wrf_file = wrf_in + ".nc"
                else:
                    wrf_file = wrf_in
                in_wrfnc = Nio.open_file(wrf_file)
        else:
            timeidx = None
            if not pynio:
                nc = NetCDF(wrf_in)
                in_wrfnc = [nc for i in xrange(repeat)]
            else:
                if not wrf_in.endswith(".nc"):
                    wrf_file = wrf_in + ".nc"
                else:
                    wrf_file = wrf_in
                nc = Nio.open_file(wrf_file)
                in_wrfnc = [nc for i in xrange(repeat)]
                
        refnc = NetCDF(referent)
                
        if testid == "xy":
            # Since this domain is not moving, the reference values are the 
            # same whether there are multiple or single files
            ref_vals = refnc.variables["ij"][:]
            # Lats/Lons taken from NCL script, just hard-coding for now
            lats = [-55, -60, -65]
            lons = [25, 30, 35]
            
            # Just call with a single lat/lon
            if single:
                xy = ll_to_xy(in_wrfnc, lats[0], lons[0])
                xy = xy + 1 # NCL uses fortran indexing
                ref = ref_vals[:,0]
                
                nt.assert_allclose(to_np(xy), ref)
                
                # Next make sure the 'proj' version works
                projparams = extract_proj_params(in_wrfnc)
                xy_proj = ll_to_xy_proj(lats[0], lons[0], **projparams)
                
                nt.assert_allclose(to_np(xy_proj), to_np(xy-1))
                
            
            else:
                xy = ll_to_xy(in_wrfnc, lats, lons)
                xy = xy + 1 # NCL uses fortran indexing
                ref = ref_vals[:]
                
                nt.assert_allclose(to_np(xy), ref)
                
                # Next make sure the 'proj' version works
                projparams = extract_proj_params(in_wrfnc)
                xy_proj = ll_to_xy_proj(lats, lons, **projparams)
                
                nt.assert_allclose(to_np(xy_proj), to_np(xy-1))
                
        else:
            # Since this domain is not moving, the reference values are the 
            # same whether there are multiple or single files
            ref_vals = refnc.variables["ll"][:]
            
             # i_s, j_s taken from NCL script, just hard-coding for now
             # NCL uses 1-based indexing for this, so need to subtract 1
            i_s = np.asarray([10, 100, 150], int) - 1
            j_s = np.asarray([10, 100, 150], int) - 1
            
            if single:
                ll = xy_to_ll(in_wrfnc, i_s[0], j_s[0])
                ref = ref_vals[::-1,0]
                
                nt.assert_allclose(to_np(ll), ref)
                
                # Next make sure the 'proj' version works
                projparams = extract_proj_params(in_wrfnc)
                ll_proj = xy_to_ll_proj(i_s[0], j_s[0], **projparams)
                
                nt.assert_allclose(to_np(ll_proj), to_np(ll))
            else:
                ll = xy_to_ll(in_wrfnc, i_s, j_s)
                ref = ref_vals[::-1,:]
                
                nt.assert_allclose(to_np(ll), ref)
                
                # Next make sure the 'proj' version works
                projparams = extract_proj_params(in_wrfnc)
                ll_proj = xy_to_ll_proj(i_s, j_s, **projparams)
                
                nt.assert_allclose(to_np(ll_proj), to_np(ll))
        
    return test

class WRFVarsTest(ut.TestCase):
    longMessage = True
    
class WRFInterpTest(ut.TestCase):
    longMessage = True
    
class WRFLatLonTest(ut.TestCase):
    longMessage = True
        

if __name__ == "__main__":
    ignore_vars = []  # Not testable yet
    wrf_vars = ["avo", "eth", "cape_2d", "cape_3d", "ctt", "dbz", "mdbz", 
                "geopt", "helicity", "lat", "lon", "omg", "p", "pressure", 
                "pvo", "pw", "rh2", "rh", "slp", "ter", "td2", "td", "tc", 
                "theta", "tk", "tv", "twb", "updraft_helicity", "ua", "va", 
                "wa", "uvmet10", "uvmet", "z", "cfrac"]
    interp_methods = ["interplevel", "vertcross", "interpline", "vinterp"]
    latlon_tests = ["xy", "ll"]
    
    try:
        import netCDF4
    except ImportError:
        pass
    else:
        for var in wrf_vars:
            if var in ignore_vars:
                continue
            
            test_func1 = make_test(var, TEST_FILE, OUT_NC_FILE)
            test_func2 = make_test(var, TEST_FILE, OUT_NC_FILE, multi=True)
            setattr(WRFVarsTest, 'test_{0}'.format(var), test_func1)
            setattr(WRFVarsTest, 'test_multi_{0}'.format(var), test_func2)
            
        for method in interp_methods:
            test_interp_func1 = make_interp_test(method, TEST_FILE, 
                                                 OUT_NC_FILE)
            test_interp_func2 = make_interp_test(method, TEST_FILE, 
                                                 OUT_NC_FILE, multi=True)
            setattr(WRFInterpTest, 'test_{0}'.format(method), 
                    test_interp_func1)
            setattr(WRFInterpTest, 'test_multi_{0}'.format(method), 
                    test_interp_func2)
        
        for testid in latlon_tests:
            for single in (True, False):
                for multi in (True, False):
                    test_ll_func = make_latlon_test(testid, TEST_FILE, 
                                                    OUT_NC_FILE, 
                                                    single=single, multi=multi, 
                                                    repeat=3, pynio=False)
                    multistr = "" if not multi else "_multi"
                    singlestr = "_nosingle" if not single else "_single"
                    test_name = "test_{}{}{}".format(testid, singlestr, 
                                                       multistr)
                    setattr(WRFLatLonTest, test_name, test_ll_func)
                
    try:
        import PyNIO
    except ImportError:
        pass
    else:
        for var in wrf_vars:
            if var in ignore_vars:
                continue
            
            test_func1 = make_test(var, TEST_FILE, OUT_NC_FILE, pynio=True)
            test_func2 = make_test(var, TEST_FILE, OUT_NC_FILE, multi=True,
                                   pynio=True)
            setattr(WRFVarsTest, 'test_pynio_{0}'.format(var), test_func1)
            setattr(WRFVarsTest, 'test_pynio_multi_{0}'.format(var), 
                    test_func2)
            
        for method in interp_methods:
            test_interp_func1 = make_interp_test(method, TEST_FILE, 
                                                 OUT_NC_FILE)
            test_interp_func2 = make_interp_test(method, TEST_FILE, 
                                                 OUT_NC_FILE, multi=True)
            setattr(WRFInterpTest, 'test_pynio_{0}'.format(method), 
                    test_interp_func1)
            setattr(WRFInterpTest, 'test_pynio_multi_{0}'.format(method), 
                    test_interp_func2)
            
        for testid in latlon_tests:
            for single in (True, False):
                for multi in (True, False):
                    test_ll_func = make_latlon_test(testid, TEST_FILE, 
                                                    OUT_NC_FILE, 
                                                    single=single, multi=multi, 
                                                    repeat=3, pynio=False)
                    multistr = "" if not multi else "_multi"
                    singlestr = "_nosingle" if not single else "_single"
                    test_name = "test_pynio_{}{}{}".format(testid, 
                                                              singlestr, 
                                                              multistr)
                    setattr(WRFLatLonTest, test_name, test_ll_func)
     
    ut.main()
    