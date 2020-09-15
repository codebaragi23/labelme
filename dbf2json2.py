# -*- coding: utf-8 -*-

import dbf
import sys
import json
import datetime

class JSONEncoder(json.JSONEncoder):
  def default(self, o):
    if isinstance(o, datetime.date):
      return o.strftime('%Y-%m-%d')

if __name__ == '__main__':
  try:
    #dbf_fn = sys.argv[1]
    dbf_fn = "./examples/hyper/WGS84_UTM zone 52N/test.dbf"
    json_fn = dbf_fn.replace('dbf', 'json')
    try:
      json_fn = sys.argv[2]
    except IndexError:
      pass
  except IndexError:
    sys.stderr.write('usage: dbf2json <dbf_filename_input> (json_filename_input)\n\t json filename is optional, will write to stdout if not given or -. If - is given for input, it will read from stdin\n')
    sys.stderr.flush()
    sys.exit(1)
  
  def get_handle(fn, mode, do_open=True):
    if fn == '-':
      if mode == 'r':
        if do_open:
          return sys.stdin
        else:
          return '/dev/stdin'
      elif mode == 'w':
        if do_open:
          return sys.stdout
        else:
          return '/dev/stdout'
    else:
      if do_open:
        return open(fn, mode, encoding='UTF8')
      else:
        return fn

  out_handle = get_handle(json_fn, 'w')

  table = dbf.Table(dbf_fn, codepage='cp949')
  table.open(dbf.READ_WRITE)
  try:
    for row in table:
      print(str(row))
    output = [str(row) for row in table]
    table.close()
  except:
    table.close()
    sys.exit(0)  

  json.dump(output, out_handle, indent=4, sort_keys=True, cls=JSONEncoder)
  out_handle.flush()
  out_handle.close()
  sys.exit(0)