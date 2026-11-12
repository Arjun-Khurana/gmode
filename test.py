import os
import json
import meep as mp
import numpy as np
import meep.mpb as mpb
from plotting import plot_eigenmode
from matplotlib import pyplot as plt

three_d = True
# parity = mp.NO_PARITY #mp.EVEN_Z if THREED else mp.ODD_Z
parity = mp.NO_PARITY #mp.EVEN_Z if THREED else mp.ODD_Z
omega = 1/1.55
num_bands = 3
resolution = 64

for parity in [
    # mp.NO_PARITY,
    # mp.EVEN_Y,
    # mp.ODD_Y,
    # mp.EVEN_Z,
    # mp.ODD_Z,
    # mp.EVEN_Y + mp.EVEN_Z,
    mp.EVEN_Y + mp.ODD_Z,
    mp.ODD_Y + mp.EVEN_Z,
    mp.ODD_Y + mp.ODD_Z,
]:
    os.makedirs(f'{str(parity)}', exist_ok=True)
    geometry = [
        # mp.Block(size=mp.Vector3(mp.inf,mp.inf), material=mp.Medium(index=1.44)),
        # mp.Block(size=mp.Vector3(0.5,0.22, mp.inf), material=mp.Medium(index=3.5)),
        mp.Block(size=mp.Vector3(mp.inf,1,0.5), material=mp.Medium(index=3.5)),
    ]

    sim = mp.Simulation(
        cell_size = mp.Vector3(1,2,2),
        resolution=resolution,
        geometry=geometry,
        default_material=mp.Medium(index=1),
        eps_averaging=False
    )

    ms = mpb.ModeSolver(
        geometry_lattice=mp.Lattice(size=mp.Vector3(0,sim.cell_size.y, sim.cell_size.z)),
        geometry=geometry,
        resolution=resolution,
        num_bands=num_bands,
        target_freq=omega,
        default_material=mp.Medium(index=1)
        # tolerance=1e-4
    )

    # Output the x component of the Poynting vector for num_bands bands at omega
    sim.init_sim()

    for i in range(num_bands):
        k = ms.find_k(parity, omega, i+1, i+1, mp.Vector3(x=1), 1e-4, omega * 3.5,
            omega * 0.1, omega * 4)
        hfields = np.real(ms.get_hfield(i+1, bloch_phase=False))
        ms.fix_field_phase()
        efields = np.real(ms.get_efield(i+1, bloch_phase=False))
        ms.fix_field_phase()
        eps_data = sim.get_array(mp.Dielectric, vol=mp.Volume(size=mp.Vector3(0,sim.cell_size.y,sim.cell_size.z)))

        Ex = efields[...,0]
        Ey = efields[...,1]
        Ez = efields[...,2]
        Hx = hfields[...,0]
        Hy = hfields[...,1]
        Hz = hfields[...,2]
        # EE = np.asarray(efields[:,:,0,0]**2 + efields[:,:,0,1]**2 + efields[:,:,0,2]**2, dtype=np.uint8)
        # HH = np.asarray(hfields[:,:,0,0]**2 + hfields[:,:,0,1]**2 + hfields[:,:,0,2]**2, dtype=np.uint8)
        max_e = np.max(efields)
        min_e = np.min(efields)
        max_h = np.max(hfields)
        min_h = np.min(hfields)
        # max_EE = np.max(EE)
        # max_HH = np.max(HH)
        # min_HH = np.min(HH)
        # min_EE = np.min(EE)

        # print(np.shape(efields))
        # print(np.shape(eps_data))
        # quit()

        # plt.figure()

        # plt.subplot(1,2,1)
        # plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        # plt.imshow(
        #     np.rot90(np.squeeze(EE)),
        #     interpolation="spline36",
        #     cmap="RdBu",
        #     vmax=max_EE,
        #     vmin=min_EE,
        #     alpha=0.5
        # )
        # plt.subplot(1,2,2)
        # plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        # plt.imshow(
        #     np.rot90(np.squeeze(HH)),
        #     interpolation="spline36",
        #     cmap="RdBu",
        #     vmax=max_HH,
        #     vmin=min_HH,
        #     alpha=0.5
        # )

        plt.subplot(3, 2, 1)
        plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        plt.imshow(
            np.rot90(np.squeeze(Ex)),
            interpolation="spline36",
            cmap="RdBu",
            vmax=max_e,
            vmin=min_e,
            alpha=0.5
        )
        plt.title("Ex")
        plt.colorbar()
        plt.subplot(3, 2, 3)
        plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        plt.imshow(
            np.rot90(np.squeeze(Ey)),
            interpolation="spline36",
            cmap="RdBu",
            vmax=max_e,
            vmin=min_e,
            alpha=0.5
        )
        plt.title("Ey")
        plt.colorbar()
        plt.subplot(3, 2, 5)
        plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        plt.imshow(
            np.rot90(np.squeeze(Ez)),
            interpolation="spline36",
            cmap="RdBu",
            vmax=max_e,
            vmin=min_e,
            alpha=0.5
        )
        plt.title("Ez")
        plt.colorbar()
        plt.subplot(3, 2, 2)
        plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        plt.imshow(
            np.rot90(np.squeeze(Hx)),
            interpolation="spline36",
            cmap="RdBu",
            vmax=max_h,
            vmin=min_h,
            alpha=0.5
        )
        plt.title("Hx")
        plt.colorbar()
        plt.subplot(3, 2, 4)
        plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        plt.imshow(
            np.rot90(np.squeeze(Hy)),
            interpolation="spline36",
            cmap="RdBu",
            vmax=max_h,
            vmin=min_h,
            alpha=0.5
        )
        plt.title("Hy")
        plt.colorbar()
        plt.subplot(3, 2, 6)
        plt.imshow(np.rot90(eps_data), interpolation='spline36', cmap='binary')
        plt.imshow(
            np.rot90(np.squeeze(Hz)),
            interpolation="spline36",
            cmap="RdBu",
            vmax=max_h,
            vmin=min_h,
            alpha=0.5
        )
        plt.title("Hz")
        plt.colorbar()
        plt.suptitle(f'neff={k[0]/omega:.04f}')
        if mp.am_really_master():
            plt.savefig(f'{parity}/mpb{i+1}.png',dpi=300)
        plt.close('all')

        f = plot_eigenmode(
            sim,
            mp.Volume(size=mp.Vector3(0,sim.cell_size.y,sim.cell_size.z)),
            band=i+1,
            direction=mp.X,
            three_d=True,
            kpoint=mp.Vector3(x=1),
            parity=parity,
            wavelength=1.55
        )
        if mp.am_really_master():
            f.savefig(f'{parity}/meep{i+1}.png',dpi=300)
        plt.close('all')
