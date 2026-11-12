import json
import meep as mp
import numpy as np
import meep.mpb as mpb
from matplotlib import pyplot as plt

# wg_w = np.linspace(0.5,1.5,10)
wg_w = [0.5]
wg_h = 0.22
omega = 1/1.55
num_bands=1
neff = np.zeros((len(wg_w), num_bands))

PX_PER_UM = 100

def calc_modes(file: str):
    with open(file, 'r') as f:
        data = json.load(f)
    print(data)
    geometry = []
    window_x, window_y = data['window']
    for (id, rect) in data['rectangles'].items():
        x1,y1,x2,y2 = rect['coords']
        x1 -= window_x/2
        x2 -= window_x/2
        y1 -= window_y/2
        y2 -= window_y/2
        geometry += [mp.Block(
            center=mp.Vector3((x1+x2)/(2*PX_PER_UM), (y1+y2)/(2*PX_PER_UM)),
            size=mp.Vector3((x2-x1)/PX_PER_UM, (y2-y1)/PX_PER_UM),
            material=mp.Medium(index=rect['index'])
        )]

    # geometry = [
    #     mp.Block(size=mp.Vector3(mp.inf,mp.inf), material=mp.Medium(index=1.44)),
    #     mp.Block(size=mp.Vector3(.5,.22), material=mp.Medium(index=3.5)),
    # ]

    sim = mp.Simulation(
        cell_size = mp.Vector3(window_x/PX_PER_UM,window_y/PX_PER_UM),
        resolution=64,
        geometry=geometry
    )
    # sim.plot2D()
    # if mp.am_really_master(): plt.show()
    # return

    ms = mpb.ModeSolver(
        geometry_lattice=mp.Lattice(size=mp.Vector3(window_x/PX_PER_UM,window_y/PX_PER_UM,0)),
        geometry=geometry,
        resolution=64,
        num_bands=num_bands,
        target_freq=omega,
        # tolerance=1e-4
    )

    parity = mp.NO_PARITY #mp.EVEN_Z if THREED else mp.ODD_Z
    # Output the x component of the Poynting vector for num_bands bands at omega
    k = ms.find_k(parity, omega, 1, num_bands, mp.Vector3(z=1), 1e-4, omega * 3.45,
            omega * 0.1, omega * 4)


    efields = np.real(ms.get_efield(1, bloch_phase=False))
    hfields = np.real(ms.get_hfield(1, bloch_phase=False))
    if mp.am_really_master():
        plt.imshow(np.rot90(efields[:,:,0,0]**2 + efields[:,:,0,1]**2 + efields[:,:,0,2]**2))
        plt.show()
    return efields, hfields
    # print(ms.freqs)
    # print(k)

    # for j in range(num_bands):
    #     neff[i,j] = k[j]/omega

# efields = []
# hfields = []
# for j in range(num_bands):
#     hfields.append(np.real(ms.get_hfield(j+1,bloch_phase=False)))
#     efields.append(np.real(ms.get_efield(j+1,bloch_phase=False)))

# print(np.shape(efields))
# efields = np.array(efields)
# if mp.am_really_master():
#     plt.imshow(efields[2,:,:,0,0])
#     plt.show()
# quit()

# quit()
# np.savez('modes.npz', neff=neff, fields=fields)
# plt.figure()
# labels = range(num_bands)
# for m in labels:
#     plt.plot(wg_w, neff[:, m], 'o-', label=str(m))

# plt.axhline(y=1.4, color='black', linestyle='--')
# plt.legend()
# plt.xlabel('Width (um)')
# plt.ylabel('Neff')
# # plt.ylim(1, 3)
# if mp.am_really_master():
#     plt.show()
#     plt.savefig('neff_moremodes.png', dpi=300)


if __name__ == '__main__':
    calc_modes('testp.json')