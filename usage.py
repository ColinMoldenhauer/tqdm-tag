from tqdm_color.tqdm_color import ErrorTqdm

N = 10
for _ in (pbar := ErrorTqdm(range(N), total=N, colour="green")):
    if _ == 1: pbar.warn()
    if _ == 90: pbar.error()
