import meep as mp
import numpy as np
from matplotlib import pyplot as plt

# plt.rcParams['figure.titlesize'] = 28
plt.rcParams['figure.autolayout'] = True # enables tight_layout() on all plots

plt.rcParams['xtick.top'] = True
plt.rcParams['ytick.right'] = True
# plt.rcParams['xtick.labelsize'] = 20
# plt.rcParams['ytick.labelsize'] = 20
plt.rcParams['xtick.direction'] = 'in'
plt.rcParams['ytick.direction'] = 'in'
plt.rcParams['xtick.major.width'] = 2
plt.rcParams['ytick.major.width'] = 2

color=['darkmagenta','goldenrod','mediumblue','forestgreen','darkcyan','darkorange']

plt.rcParams['axes.linewidth'] = 1.5
plt.rcParams['axes.titlesize'] = 24
plt.rcParams['axes.labelsize'] = 14
plt.rcParams['axes.prop_cycle'] = plt.cycler(color=color)

plt.rcParams['lines.linewidth'] = 2

def plot_eigenmode(
        sim:mp.Simulation,
        geometry_lattice,
        band: int = 1,
        direction: int = mp.X,
        three_d: bool = False,
        kpoint: mp.Vector3() = None,
        parity = mp.NO_PARITY,
        wavelength: float = 0.85
        # save: bool = True,
    ) -> plt.Figure:
        """
        Function to plot the eigenmodes of the input/output waveguides for debugging purposes (especially when specifying parities)
        TODO: generate the array that I want to pull from EigenmodeData such that it is three dimensional
        but is nonzero in only two dimensions so the eigenmode plotter will show up regardless of which
        dimension the mode is plotted in.
        TODO: include the direction (or infer from the geometry lattice)
        """
        res = sim.resolution
        # at least of of these dimensions will be singleton and will eventually be removed to make a 2D image
        Nx = int(np.round(geometry_lattice.size.x * res)) +1
        Ny = int(np.round(geometry_lattice.size.y * res)) +1
        Nz = int(np.round(geometry_lattice.size.z * res))

        Nx = 1 if Nx == 0 else Nx
        Ny = 1 if Ny == 0 else Ny
        Nz = 1 if Nz == 0 else Nz

        Ex = np.zeros([Nx, Ny, Nz])  # arrays to store the data
        Ey = np.zeros([Nx, Ny, Nz])  # arrays to store the data
        Ez = np.zeros([Nx, Ny, Nz])  # arrays to store the data
        Hx = np.zeros([Nx, Ny, Nz])  # arrays to store the data
        Hy = np.zeros([Nx, Ny, Nz])  # arrays to store the data
        Hz = np.zeros([Nx, Ny, Nz])  # arrays to store the data
        eps_data = np.zeros([Nx, Ny, Nz])  # arrays to store the data

        # TODO: find a better way that a match statement
        if not kpoint:
            match direction:
                case mp.X:
                    kpoint = wavelength * mp.Vector3(1, 0, 0)
                case mp.Y:
                    kpoint = wavelength * mp.Vector3(0, 1, 0)
                case mp.Z:
                    kpoint = wavelength * mp.Vector3(0, 0, 1)
                case _:
                    raise TypeError("Provide a direction (mp.X, mp.Y, or mp.Z)")

        sim.init_sim()
        if mp.am_really_master(): print('Sim Init')
        data = sim.get_eigenmode(
            frequency=1 / wavelength,
            match_frequency=True,
            direction=direction,
            where=geometry_lattice,
            band_num=band,
            parity=parity,
            kpoint=kpoint,
            resolution=res,
            eigensolver_tol=1e-12,
        )

        x = np.linspace(
            geometry_lattice.center.x - geometry_lattice.size.x / 2,
            geometry_lattice.center.x + geometry_lattice.size.x / 2,
            Nx,
        )
        y = np.linspace(
            geometry_lattice.center.y - geometry_lattice.size.y / 2,
            geometry_lattice.center.y + geometry_lattice.size.y / 2,
            Ny,
        )
        z = np.linspace(
            geometry_lattice.center.z - geometry_lattice.size.z / 2,
            geometry_lattice.center.z + geometry_lattice.size.z / 2,
            Nz,
        )

        for i in range(Nx):
            for j in range(Ny):
                for k in range(Nz):
                    Ex[i, j, k] = np.real(
                        data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Ex)
                    )
                    Ey[i, j, k] = np.real(
                        data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Ey)
                    )
                    Ez[i, j, k] = np.real(
                        data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Ez)
                    )
                    Hx[i, j, k] = np.real(
                        data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Hx)
                    )
                    Hy[i, j, k] = np.real(
                        data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Hy)
                    )
                    Hz[i, j, k] = np.real(
                        data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Hz)
                    )
                    # eps_data[i, j, k] = np.real(
                    #     data.amplitude(point=mp.Vector3(x[i], y[j], z[k]), component=mp.Dielectric)
                    # )

        eps_data = sim.get_array(vol=geometry_lattice, component=mp.Dielectric)

        # title = "No Parity"
        # elif self.hp.geo.eig_parity == 1: title = "EVEN Z"
        # elif self.hp.geo.eig_parity == 2: title = "ODD Z"
        # elif self.hp.geo.eig_parity == 4: title = "EVEN Y"
        # elif self.hp.geo.eig_parity == 5: title = "EVEN Y and EVEN Z"
        # elif self.hp.geo.eig_parity == 6: title = "EVEN Y and ODD Z"
        # elif self.hp.geo.eig_parity == 8: title = "ODD Y"
        # elif self.hp.geo.eig_parity == 9: title = "ODD Y and EVEN Z "
        # elif self.hp.geo.eig_parity == 10: title = "ODD Y and ODD Z"

        # title += f", Band {band}"
        # title = f"n_g={1/data.group_velocity:.04f}"
        # title += f", k=({data.kdom.x:.06f}, {data.kdom.y:.06f}, {data.kdom.z:.06f})"
        omega = 1/wavelength
        # data.k
        title = f"neff={np.sqrt(data.k.x**2 + data.k.y**2 + data.k.z**2) / omega:.04f}"

        eig_mode_fig = plt.figure(figsize=(6, 4))
        plt.suptitle(title, fontsize=20)

        max_e = np.max([Ex, Ey, Ez])
        min_e = np.min([Ex, Ey, Ez])
        max_h = np.max([Hx, Hy, Hz])
        min_h = np.min([Hx, Hy, Hz])
        # print(np.shape(Ex))
        
        if three_d:
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

        else:
            plt.subplot(3, 2, 1)
            plt.plot(np.squeeze(Ex))
            plt.ylim([min_e, max_e])
            plt.title("Ex")
            plt.subplot(3, 2, 3)
            plt.plot(np.squeeze(Ey))
            plt.ylim([min_e, max_e])
            plt.title("Ey")
            plt.subplot(3, 2, 5)
            plt.plot(np.squeeze(Ez))
            plt.ylim([min_e, max_e])
            plt.title("Ez")
            plt.subplot(3,2,2)
            plt.plot(np.squeeze(np.power(Ex,2) + np.power(Ey,2) + np.power(Ez,2)))
            plt.title('$|E|^2$')
            plt.subplot(3, 2, 4)
            plt.plot(eps_data)
            plt.title("Dielectric")

        plt.tight_layout()
        plt.close()
        return eig_mode_fig