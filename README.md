# photosort
Py script using JPG EXIF GPS data to create photo directory structure

It's called "dps.py" for dropbox photo sort, since I use this for structuring my Dropbox Camera Uploads/ folder (which is synch'd from my iPhone). I run the script with a LaunchAgent weekly.

The Reverse Geocoding is using OpenStreetMaps webservice which is slow but free. I also coded an Google Maps API option that requires an API key.

The geocoding data is cached using a sqllite db stored inside the sorted folder structure (.dps_storage.db). Only new (uncached) photos will be reserse-geocoded through the web api. If the cache file is removed or deleted, the entire photo library will be looked up again. The DB is also easily modifiable with sqllite. The table is called 'storage'. The keys in the table are a hash of the image filename and modification date. Thus you should be able to 'touch' a file and force it to be looked up again (recached).

The files are sorted by Date and Location using 5 parameters: Year, Month, Country, State, Locality/City. These are abbreviated YMCSL, respectively. The directory structure (sort) is, by default, in that order, but can be modified using a command-line option.

To prevent lots of directories, with few files, the algorithm collapses directories with only a few (specifcally 4) entries (sub-directories or files). The algorithm will always keep at least 2 levels (year and month, in the default sort order). Both these limits are also modifiable.

Requires Pillow python image library. Install with `$ pip install Pillow`

If using Google maps API, you'll need to provide the Google API key in the command line and have Google MAPS python module installed as well. https://github.com/googlemaps/google-maps-services-python

Install with `$ pip install -U googlemaps`

***
```
usage: dps.py [-h] [--storage-levels STORAGE_LEVELS]
              [--storage-min STORAGE_MIN] [--dry-run] [--show-collapse]
              [--order ORDER] [--google GOOGLE] [--show-cached]
              directory

positional arguments:
  directory             Directory containing photos to be rearranged

optional arguments:
  -h, --help            show this help message and exit
  --storage-levels STORAGE_LEVELS
                        Minimum number of subdirectories
  --storage-min STORAGE_MIN
                        Minimum number of items in subdirectory before
                        collapsing
  --dry-run             Calculate directory structure without moving files
  --show-collapse       Display directory structure before collapsing
  --order ORDER         Default directory structure. Must be permutation of
                        'YMCSL'. Y=Year; M=Month; C=Country; S=State;
                        L=Locality/City
  --google GOOGLE       Google Maps API Key. Specify this key to use Google
                        Maps reverse geo-code service
  --show-cached         Show cached (previous) elements in directory structure
```





