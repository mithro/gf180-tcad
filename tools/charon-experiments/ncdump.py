"""Print the header (dimensions, variables, attributes) of a netCDF/Exodus file."""
import sys
import netCDF4
ds = netCDF4.Dataset(sys.argv[1])
print("format", ds.data_model, ds.file_format)
for k in ds.ncattrs():
    print("gattr", k, repr(ds.getncattr(k)))
for n, d in ds.dimensions.items():
    print("dim", n, len(d), "unlimited" if d.isunlimited() else "")
for n, v in ds.variables.items():
    print("var", n, v.dtype, v.dimensions, {a: v.getncattr(a) for a in v.ncattrs()})
for n in sys.argv[2:]:
    v = ds.variables[n]
    v.set_auto_mask(False)
    print(n, repr(v[:]))
