from sys import argv
from json import loads, dump


inp = argv[-1]

with open(inp) as like:
    loaded = loads(like.read())
    copy = dict(loaded)

    for l, metric in enumerate(loaded['metrics']):
        for key in metric.keys():
            times = metric[key]['times']
            starts = times['start']
            ends = times['end']

            diff = ends - starts
            copy['metrics'][l][key]['times'] = diff

    print(copy)
