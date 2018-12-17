# dropbox-photo-sorter
# (c)2018 Matthew Flanzer
# License: MIT
import sys
import re
import os
import shutil
from PIL import Image
import datetime
import time
import PIL.ExifTags
import sqlite3
import requests
import json
import unidecode
import argparse


class Storage:
    def __init__(self, pathname):
        self.year = None
        self.month = None
        self.country = None
        self.state = None
        self.city = None
        if pathname:
            unix = os.path.getmtime(pathname)
            dt = datetime.datetime.utcfromtimestamp(unix)
            self.year = "{:%Y}".format(dt)
            self.month = "{:%m}".format(dt)
        self.cached = False
    def dict(self):
        return {'year':self.year,'month':self.month,'country':self.country,'state':self.state,'city':self.city}
    def __str__(self):
        return str(self.dict())
    def __getitem__(self,key):
        return self.dict()[key]
    def item(self,key):
        if key=='y':
            return self.year
        elif key=='m':
            return self.month
        elif key=='c':
            return self.country
        elif key=='s':
            return self.state
        elif key=='l':
            return self.city
        else:
            return None

class Node:
    prefixsz = 8
    def __init__(self):
        self.children={}
        self.value = []
    def isLeaf(self):
        return len(self.children)==0
    def add(self,k):
        if k is None:
            return self
        if not k in self.children:
            self.children[k] = Node()
        return self.children[k]
    def merge(self,n):
        for k,v in n.children.iteritems():
            if k in self.children:
                self.children[k].merge(v)
            else:
                self.children[k] = v
        self.value += n.value
    def flatten(self):
        new_node = Node()
        for k,v in self.children.iteritems():
            new_node.merge(v)
        self.children = new_node.children
        self.value += new_node.value
    def collapse(self,level,minimum,current,show_collapse):
        num_children = len(self.children)
        for k,n in self.children.items():
            n.collapse(level,minimum,current+1,show_collapse)
            if (n.size() < minimum) and (current >= level-1):
                if show_collapse:
                    print "flattening %s at %d with %s"%(k,current,n.children.keys())
                n.flatten()
            if (num_children < minimum) and (n.size() < minimum) and (current >= level):
                if show_collapse:
                    print "merging %s at %d with %s"%(k,current,n.children.keys())
                self.merge(n)
                del self.children[k]
    def dict(self,full_path):
        rtrn = {}
        for v, cached in self.value:
            rtrn[v] = os.path.basename(v) if full_path else ''
        for k,n in self.children.iteritems():
            for dk,dv in n.dict(full_path).iteritems():
                rtrn[dk] = "%s/%s"%(k,dv)
        return rtrn
    def dump(self,show_cached=True,level=0):
        prefix = ' ' * (Node.prefixsz * level)
        if self.value:
            for v, cached in self.value:
                if not cached or show_cached:
                    print prefix+os.path.basename(v)
        for k,n in self.children.iteritems():
            cached,non_cached = n.count_cached()
            if (non_cached > 0) or show_cached:
                print "%s%s/"%(prefix,k)
                n.dump(show_cached,level+1)
    def count_cached(self):
        cached = 0
        non_cached = 0
        if self.value:
            cached = len(filter(lambda (v,c): c, self.value))
            non_cached = len(self.value) - cached
        for k,n in self.children.iteritems():
            (sub_cached, sub_non_cached) = n.count_cached()
            cached += sub_cached
            non_cached += sub_non_cached
        return (cached, non_cached)
    def size(self):
        return len(self.value) + len(self.children)




        
    





class StorageTree:
    default_mode='ymcsl'
    def __init__(self,stores,mode=default_mode):
        self.head = Node()
        for k,v in stores.iteritems():
            node = self.head
            for m in mode:
                node = node.add(v.item(m))
            node.value.append((k,v.cached))
    def dict(self,full_path):
        return self.head.dict(full_path)
    def dump(self,show_cached=True):
        self.head.dump(show_cached)
    def collapse(self,level,minimum,show_collapse):
        self.head.collapse(level,minimum,0,show_collapse)
    @classmethod
    def fromDirectory(cls,root,fd,cache,mode,google):
        stores = {} 
        if fd:
            fd.write('Processing ')
        lfileext = lambda f: os.path.splitext(f)[1].lower()
        all_files = [os.path.join(d,filename) for d, _, files in os.walk(root) for filename in files  if lfileext(filename) in ('.jpg','.jpeg')]
        progress = Progress(all_files,fd)
        for pathname in progress:
            s = cache.get(pathname) if cache else None
            if s is None:
                s = Storage(pathname)
                try:
                    im = Image.open(pathname)
                    exif = ExifData(im._getexif())
                    if exif.year and exif.month:
                        s.year = exif.year
                        s.month = exif.month
                    if exif.lat and exif.lon:
                        if google is None:
                            (s.city,s.state,s.country) = GeoCoderOpenStreetmap(exif.lat,exif.lon).loc
                        else:
                            (s.city,s.state,s.country) = GeoCoderGoogle(exif.lat,exif.lon,google).loc

                    #print "%s: %s"%(filename,s)
                except Exception as e:
                    #print "Exception %s: %s" %(filename,str(e))
                    pass
                if cache:
                    cache.put(pathname,s)
            stores[pathname] = s
        if cache:
            cache.flush()
        return cls(stores,mode)

class ExifData:
    def __init__(self,exifraw):
        if 0x0132 in exifraw:
            self.year = exifraw[0x0132][:4]
            self.month = exifraw[0x0132][5:7]
        else:
            self.year = None
            self.month = None
        if 0x8825 in exifraw:
            gpsraw = exifraw[0x8825]
            self.lat = ExifData.degrees(gpsraw[2],gpsraw[1]=='S')
            self.lon = ExifData.degrees(gpsraw[4],gpsraw[3]=='W')
        else:
            self.lat = None
            self.lon = None

    @staticmethod
    def degrees(raw,neg):
        ((degreesNumerator, degreesDenominator),
        (minutesNumerator, minutesDenominator), 
        (secondsNumerator, secondsDenominator)) = raw
        Degrees = (float(degreesNumerator) / float(degreesDenominator))
        Minutes = (float(minutesNumerator) / float(minutesDenominator))
        Seconds = (float(secondsNumerator) / float(secondsDenominator))
        dd = Degrees + Minutes/60.0 + Seconds/3600.0
        if neg:
            dd *= -1.0
        return dd



class Cache:
    def __init__(self,rootdir,use_pending=False):
        self.conn = sqlite3.connect(os.path.join(rootdir,'.dps_storage.db'))
        cursor = self.conn.cursor()
        sql = """
            CREATE TABLE IF NOT EXISTS storage (
                hash int PRIMARY KEY,
                year text,
                month text,
                country text,
                state text,
                city text,
                filename text
            );
        """
        cursor.execute(sql)
        self.conn.commit()
        #print "created table storage"
        self.pending = {}
        self.use_pending = use_pending

    def __getitem__(self,h):
        cursor = self.conn.cursor()
        sql = """
            SELECT year, month, country, state, city
            FROM storage
            WHERE hash = ?
            ;
        """
        cursor.execute(sql,(h,))
        row = cursor.fetchone()
        #print "found "+str(row)
        if row is None:
            return None
        s = Storage(None)
        (s.year, s.month, s.country, s.state, s.city) = row
        s.cached = True
        return s
    def __contains__(self,h):
        s = self[h]
        return s is not None
    def get(self,pathname):
        h = self.make_hash(pathname)
        return self.__getitem__(h)
    def make_hash(self,pathname):
        mtime = os.path.getmtime(pathname)
        filename = os.path.basename(pathname)
        return hash((filename,mtime))
    def __setitem__(self,h,(filename,s)):
        cursor = self.conn.cursor()
        sql = """
            INSERT INTO storage(hash, year, month, country, state, city, filename) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        cursor.execute(sql, (h, s.year, s.month, s.country, s.state, s.city, filename))
        self.conn.commit()
        #print "insert "+str(h)
        return s
    def put(self,pathname,s):
        h = self.make_hash(pathname)
        filename = os.path.basename(pathname)
        if self.use_pending:
            self.pending[h] = (filename,s)
            return s
        else:
            return self.__setitem__(h,(filename,s))
    def dump(self):
        cursor = self.conn.cursor()
        sql = """
            SELECT * FROM storage;
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        print rows
    def flush(self):
        if len(self.pending) > 0:
            cursor = self.conn.cursor()
            sql = "INSERT INTO storage(hash, year, month, country, state, city,filename) VALUES "
            results = []
            sqlext = []
            for (k,(f,v)) in self.pending.iteritems():
                sqlext.append("(?, ?, ?, ?, ?, ?, ?)")
                results.append(k)
                results.append(v.year)
                results.append(v.month)
                results.append(v.country)
                results.append(v.state)
                results.append(v.city)
                results.append(f)
            sql += ",".join(sqlext)    
            sql += ";"
            cursor.execute(sql,results)
            self.conn.commit()
            self.pending = {}

class Progress:
    def __init__(self,lst,fd):
        self.lst = lst
        self.sz = len(self.lst)
        try:
            if fd.isatty():
                self.fd = fd
            else:
                self.fd = None
        except:
            self.fd = None
    def __iter__(self):
        start = datetime.datetime.now()
        last_len = 0
        s=''
        for (i,x) in enumerate(self.lst):
            yield x
            elapsed = datetime.datetime.now() - start
            if i+1 == self.sz: # last one
                predict_display = " in %s"%(str(elapsed)[:7])
            elif i > 2:
                rate = float(i)/elapsed.total_seconds()
                predict = datetime.timedelta(seconds = float(self.sz-i) / rate)
                predict_display = " (%.2f fps, %s remaining)"%(rate,str(predict)[:7])
            else:
                predict_display = ''
            s = "%d/%d%s"%(i+1,self.sz,predict_display)
            if self.fd:
                back = chr(8)*last_len
                self.fd.write(back+s)
                this_len = len(s)
                if this_len < last_len:
                    self.fd.write(' '*(last_len-this_len))
                else:
                    last_len = this_len
                self.fd.flush()
        if self.fd:
            self.fd.write('\n')
            self.fd.flush()
        else:
            print s

class GeoCoder(object):
    def __init__(self,lat,lon):
        self.loc = (None,None,None)

class GeoCoderGoogle(GeoCoder):
    def __init__(self,lat,lon,key):
        import googlemaps
        super(GeoCoderGoogle,self).__init__(lat,lon)
        # Look up an address with reverse geocoding
        gmaps = googlemaps.Client(key=key)
        reverse_geocode_result = gmaps.reverse_geocode((lat,lon))
        address = reverse_geocode_result[0]['address_components']
        city = GeoCoderGoogle.address_part(address,'locality')
        state = GeoCoderGoogle.address_part(address,'administrative_area_level_1')
        country = GeoCoderGoogle.address_part(address,'country')
        self.loc=(city,state,country)
    @staticmethod
    def address_part(address,key):
        for d in address:
            if key in d['types']:
                return d['long_name']
        return None


class GeoCoderOpenStreetmap(GeoCoder):
    def __init__(self,lat,lon):
        super(GeoCoderOpenStreetmap,self).__init__(lat,lon)
        r = requests.get("https://nominatim.openstreetmap.org/reverse?format=json&lat=%f&lon=%f&zoom=18&addressdetails=1"%(lat,lon))
        nom = json.loads(r.text)
        address = nom['address']
        try:
            city = unidecode.unidecode(address['city'])
        except:
            city = None
        try:
            state = unidecode.unidecode(address['state'])
        except:
            state = None
        try:
            country = unidecode.unidecode(address['country'])
        except:
            country = None
        self.loc= (city,state,country)

        
def move_files(args):
    (root, storage_levels, storage_min, show_collapse, dry_run, mode, google, show_cached) = (args.directory,args.storage_levels,args.storage_min,args.show_collapse,args.dry_run,args.order,args.google, args.show_cached)
    storage_tree = StorageTree.fromDirectory(root,sys.stdout,Cache(root),mode,google)
    if show_collapse:
        storage_tree.dump(show_cached)
        print 'collapsing {} levels at least {} entries'.format(storage_levels,storage_min)
    storage_tree.collapse(storage_levels,storage_min,show_collapse)
    storage_tree.dump(show_cached)
    for k,v in storage_tree.dict(True).iteritems():
        d = os.path.join(root,os.path.dirname(v))+"/"
        #print "Making directory %s"%d
        if not dry_run:
            try:
                os.makedirs(os.path.dirname(d))
            except Exception as e:
                #print str(e)
                pass
        dst = os.path.join(root,v)
        if k != dst:
            print "%s->%s"%(k,v)
            if not dry_run:
                try:
                    shutil.move(k,dst)
                except Exception as e:
                    print str(e)
        
def env(key,default):
    try:
        val = os.environ[key]
        if isinstance(default,bool):
            return val.lower() == 'true'
        elif isinstance(default,int):
            return int(val)
        else:
            return val
    except:
        return default

def main():
    try:
        # create the args list
        parser = argparse.ArgumentParser()
        parser.add_argument('--storage-levels',type=int,default=env('STORAGE_LEVELS',2),help="Minimum number of subdirectories")
        parser.add_argument('--storage-min',type=int,default=env('STORAGE_MIN',4),help="Minimum number of items in subdirectory before collapsing")
        parser.add_argument('--dry-run',default=env('DRY_RUN',False),action="store_true",help="Calculate directory structure without moving files")
        parser.add_argument('--show-collapse',default=env('SHOW_COLLAPSE',False),action="store_true",help="Display directory structure before collapsing")
        parser.add_argument('--order',default=StorageTree.default_mode,help="Default directory structure. Must be permutation of 'YMCSL'. Y=Year; M=Month; C=Country; S=State; L=Locality/City")
        parser.add_argument('--google',default=env('GOOGLE_API_KEY',None),help="Google Maps API Key. Specify this key to use Google Maps reverse geo-code service")
        parser.add_argument('directory',help="Directory containing photos to be rearranged")
        parser.add_argument('--show-cached',default=env('SHOW_CACHED',False),action="store_true",help="Show cached (previous) elements in directory structure")
        args = parser.parse_args()

        # check the order
        args.order=args.order.lower()
        oc = [0]*128
        for ch in args.order:
            oc[ord(ch)] += 1
        for (i,cc) in enumerate(oc):
            if cc > (1 if chr(i) in StorageTree.default_mode else 0):
                raise RuntimeError("Invalid argument for --order. Must be permutation of 'YMCSL'")
        
        # move the files
        move_files(args)
        print "This is DropBoxPhotoSorter"
        #cache_.dump()
        return 0
    except Exception as e:
        print e
        import traceback
        tb = traceback.format_exc()
        print tb
        return -1

if __name__=='__main__':
    sys.exit(main())



