"""Optimal transport on a pixel grid by log-domain Sinkhorn with separable kernels, with epsilon scaling.

transport_map(T) returns, for every cell of a uniformly lit square, the point on the wall (in cell units) its light
must reach so that the wall brightness becomes T. The map is the barycentric projection of the entropic plan; its
blur is about sqrt(eps_final) cells.
"""
import numpy as np, torch

def transport_map(T, eps_final=0.5, iters_per=40, final_iters=400, device=None, log=True):
    dev = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    n = T.shape[0]
    x = torch.arange(n, dtype=torch.float32, device=dev)
    C = 0.5 * (x[:, None] - x[None, :]) ** 2                       # C[a, b] = |a - b|^2 / 2
    lmu = torch.full((n, n), -2 * np.log(n), dtype=torch.float32, device=dev)   # uniform source
    nu = torch.tensor(T / T.sum(), dtype=torch.float32, device=dev)
    lnu = torch.log(nu)
    f = torch.zeros((n, n), device=dev); g = torch.zeros((n, n), device=dev)

    def softmin(h, eps):
        # out[x1, x2] = -eps * log sum_{y1,y2} exp(h[y1, y2] / eps... ) with separable cost, h already includes /eps
        A = torch.logsumexp(h[:, None, :] - C[None, :, :] / eps, dim=2)        # [y1, x2]
        return torch.logsumexp(A.T[:, None, :] - C[None, :, :] / eps, dim=2).T  # [x1, x2]

    eps = float(n * n) / 4
    stages = []
    while eps > eps_final:
        stages.append(eps); eps *= 0.6
    stages.append(eps_final)
    for k, eps in enumerate(stages):
        its = final_iters if k == len(stages) - 1 else iters_per
        for _ in range(its):
            f = -eps * softmin(g / eps + lnu, eps)
            g = -eps * softmin(f / eps + lmu, eps)
        if log:
            print(f"  eps {eps:10.3f}", flush=True)
    # barycentric projection: E[y1 | x], E[y2 | x]
    h = g / eps + lnu
    A = torch.logsumexp(h[:, None, :] - C[None, :, :] / eps, dim=2)                     # [y1, x2]
    Z = torch.logsumexp(A.T[:, None, :] - C[None, :, :] / eps, dim=2).T                # [x1, x2]
    ly = torch.log(x + 1.0)
    Y1 = torch.exp(torch.logsumexp((A + ly[:, None]).T[:, None, :] - C[None, :, :] / eps, dim=2).T - Z) - 1.0
    B = torch.logsumexp((h + ly[None, :])[:, None, :] - C[None, :, :] / eps, dim=2)     # [y1, x2] weighted by y2
    Y2 = torch.exp(torch.logsumexp(B.T[:, None, :] - C[None, :, :] / eps, dim=2).T - Z) - 1.0
    return Y1.cpu().numpy().astype(np.float64), Y2.cpu().numpy().astype(np.float64)
