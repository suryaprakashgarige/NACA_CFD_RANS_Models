#!/usr/bin/env python3
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
import sys
import shutil
import re
import numpy as np

def setup_sweep_case(airfoil, model, alpha_deg, prev_case=None):
    cases_root = os.path.join(PROJECT_ROOT, "cases")
    mesh_root = os.path.join(PROJECT_ROOT, "mesh")
    
    alpha_str = f"a{int(round(alpha_deg)):02d}"
    case_dir = os.path.join(cases_root, airfoil, model, alpha_str)
    
    os.makedirs(case_dir, exist_ok=True)
    os.makedirs(os.path.join(case_dir, "constant"), exist_ok=True)
    os.makedirs(os.path.join(case_dir, "system"), exist_ok=True)
    os.makedirs(os.path.join(case_dir, "0"), exist_ok=True)

    # 1. Mesh: copy polyMesh from mesh/<airfoil>/L2/constant/polyMesh
    src_mesh = os.path.join(mesh_root, airfoil, "L2", "constant", "polyMesh")
    dst_mesh = os.path.join(case_dir, "constant", "polyMesh")
    os.makedirs(dst_mesh, exist_ok=True)
    for fname in ["points", "faces", "owner", "neighbour", "boundary"]:
        src_f = os.path.join(src_mesh, fname)
        dst_f = os.path.join(dst_mesh, fname)
        if not os.path.exists(dst_f):
            try:
                os.link(src_f, dst_f)
            except Exception:
                shutil.copy2(src_f, dst_f)

    # 2. Flow and angle of attack parameters
    U_mag = 52.08
    nu = 8.68e-06
    alpha_rad = np.radians(alpha_deg)
    ux = U_mag * np.cos(alpha_rad)
    uy = U_mag * np.sin(alpha_rad)
    
    lift_x = -np.sin(alpha_rad)
    lift_y = np.cos(alpha_rad)
    drag_x = np.cos(alpha_rad)
    drag_y = np.sin(alpha_rad)

    # Iteration limits
    if alpha_deg >= 14.5:
        max_iter = 4000  # Capped at 4,000 per user rule
    else:
        max_iter = 2500

    # 3. constant/physicalProperties
    with open(os.path.join(case_dir, "constant", "physicalProperties"), "w") as f:
        f.write(f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      physicalProperties;
}}

viscosityModel  constant;
nu              {nu:.6e};
""")

    # 4. constant/momentumTransport
    model_name = "SpalartAllmaras" if model == "SA" else "kOmegaSST"
    with open(os.path.join(case_dir, "constant", "momentumTransport"), "w") as f:
        f.write(f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      momentumTransport;
}}

simulationType  RAS;

RAS
{{
    model           {model_name};
    turbulence      on;
    printCoeffs     on;
}}
""")

    # 5. system/controlDict
    with open(os.path.join(case_dir, "system", "controlDict"), "w") as f:
        f.write(f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}

application     foamRun;
solver          incompressibleFluid;

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {max_iter};
deltaT          1;

writeControl    timeStep;
writeInterval   10000;
purgeWrite      1;

writeFormat     ascii;
writePrecision  7;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    forceCoeffs
    {{
        type            forceCoeffs;
        libs            ("libforces.so");
        writeControl    timeStep;
        writeInterval /*fc*/ 1;
        patches         (airfoil);
        rho             rhoInf;
        rhoInf          1;
        magUInf         {U_mag};
        lRef            1.0;
        Aref            0.1;
        CofR            (0.25 0 0);
        pitchAxis       (0 0 -1);
        liftDir         ({lift_x:.8f} {lift_y:.8f} 0);
        dragDir         ({drag_x:.8f} {drag_y:.8f} 0);
    }}

    yPlus
    {{
        type            yPlus;
        libs            ("libfieldFunctionObjects.so");
        writeControl    writeTime;
    }}
}}
""")

    # 6. system/fvSchemes
    with open(os.path.join(case_dir, "system", "fvSchemes"), "w") as f:
        f.write("""FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         cellLimited Gauss linear 1;
    grad(U)         cellLimited Gauss linear 1;
    grad(k)         cellLimited Gauss linear 1;
    grad(omega)     cellLimited Gauss linear 1;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,nuTilda) bounded Gauss linearUpwind default;
    div(phi,k)      Gauss limitedLinear 1;
    div(phi,omega)  Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
    div(nonlinearStress) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

wallDist
{
    method          meshWave;
}
""")

    # 7. system/fvSolution
    relax_p = 0.2 if alpha_deg >= 14.5 else 0.3
    relax_u = 0.5 if alpha_deg >= 14.5 else 0.7
    relax_turb = 0.3 if model == 'SST' else (0.5 if alpha_deg >= 14.5 else 0.7)
    with open(os.path.join(case_dir, "system", "fvSolution"), "w") as f:
        f.write(f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}}

solvers
{{
    p
    {{
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.05;
        smoother        GaussSeidel;
        nPreSweeps      0;
        nPostSweeps     2;
        cacheAgglomeration true;
        agglomerator    faceAreaPair;
        nCellsInCoarsestLevel 10;
        mergeLevels     1;
    }}

    "(U|nuTilda|k|omega)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-08;
        relTol          0.1;
    }}
}}

SIMPLE
{{
    nNonOrthogonalCorrectors 1;
    consistent      yes;

    residualControl
    {{
        p               1e-08;
        U               1e-08;
        "(nuTilda|k|omega)" 1e-08;
    }}
}}

relaxationFactors
{{
    fields
    {{
        p               {relax_p};
    }}
    equations
    {{
        U               {relax_u};
        "(nuTilda|k|omega)" {relax_turb};
    }}
}}
""")

    # 8. system/decomposeParDict
    with open(os.path.join(case_dir, "system", "decomposeParDict"), "w") as f:
        f.write("""FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      decomposeParDict;
}

numberOfSubdomains 3;
method          scotch;
""")

    # 9. Initial Fields (0/): Check continuation from prev_case
    latest_prev_time = None
    if prev_case and os.path.exists(prev_case):
        # Find latest reconstructed numerical time directory in prev_case
        time_dirs = []
        for item in os.listdir(prev_case):
            try:
                t_val = float(item)
                if t_val > 0 and os.path.isdir(os.path.join(prev_case, item)):
                    time_dirs.append((t_val, item))
            except ValueError:
                pass
        if time_dirs:
            time_dirs.sort(key=lambda x: x[0])
            latest_prev_time = os.path.join(prev_case, time_dirs[-1][1])

    if latest_prev_time:
        print(f"Continuation: Initializing {case_dir} from {latest_prev_time}")
        # Copy fields from previous time directory
        for fname in ["p", "U", "nut"]:
            src = os.path.join(latest_prev_time, fname)
            dst = os.path.join(case_dir, "0", fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        if model == "SA":
            src = os.path.join(latest_prev_time, "nuTilda")
            dst = os.path.join(case_dir, "0", "nuTilda")
            if os.path.exists(src):
                shutil.copy2(src, dst)
        else:
            for fname in ["k", "omega"]:
                src = os.path.join(latest_prev_time, fname)
                dst = os.path.join(case_dir, "0", fname)
                if os.path.exists(src):
                    shutil.copy2(src, dst)

        # Update boundary condition in 0/k with kqRWallFunction for SST
        if model == "SST":
            k_file = os.path.join(case_dir, "0", "k")
            if os.path.exists(k_file):
                with open(k_file, "r") as kf:
                    k_text = kf.read()
                k_text = re.sub(
                    r"airfoil\s*\{[^}]*?(?:\([^)]*?\)[^}]*?)?\}",
                    '''airfoil
    {
        type            kqRWallFunction;
        value           uniform 1e-10;
    }''',
                    k_text
                )
                with open(k_file, "w") as kf:
                    kf.write(k_text)

        # Update boundary condition in 0/U with new rotated freestream
        u_file = os.path.join(case_dir, "0", "U")
        if os.path.exists(u_file):
            with open(u_file, "r") as f:
                u_text = f.read()
            u_text = re.sub(r"freestreamValue\s+uniform\s+\([^)]+\);", f"freestreamValue uniform ({ux:.6f} {uy:.6f} 0);", u_text)
            with open(u_file, "w") as f:
                f.write(u_text)
    else:
        # Fresh initialization from scratch
        print(f"Fresh initialization: {case_dir}")
        # 0/p
        with open(os.path.join(case_dir, "0", "p"), "w") as f:
            f.write("""FoamFile
{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      p;
}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    airfoil
    {
        type            zeroGradient;
    }
    farfield
    {
        type            freestreamPressure;
        freestreamValue uniform 0;
    }
    frontAndBack
    {
        type            empty;
    }
}
""")
        # 0/U
        with open(os.path.join(case_dir, "0", "U"), "w") as f:
            f.write(f"""FoamFile
{{
    format      ascii;
    class       volVectorField;
    location    "0";
    object      U;
}}
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({ux:.6f} {uy:.6f} 0);
boundaryField
{{
    airfoil
    {{
        type            noSlip;
    }}
    farfield
    {{
        type            freestream;
        freestreamValue uniform ({ux:.6f} {uy:.6f} 0);
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
""")
        # 0/nut
        nut_far = 3.0 * nu if model == "SST" else 0.0
        nut_wall_type = "nutLowReWallFunction" if model == "SST" else "calculated"
        with open(os.path.join(case_dir, "0", "nut"), "w") as f:
            f.write(f"""FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nut;
}}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform {nut_far:.6e};
boundaryField
{{
    airfoil
    {{
        type            {nut_wall_type};
        value           uniform 0;
    }}
    farfield
    {{
        type            calculated;
        value           uniform {nut_far:.6e};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
""")
        if model == "SA":
            with open(os.path.join(case_dir, "0", "nuTilda"), "w") as f:
                f.write("""FoamFile
{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nuTilda;
}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 2.604e-05;
boundaryField
{
    airfoil
    {
        type            kqRWallFunction;
        value           uniform 1e-10;
    }
    farfield
    {
        type            freestream;
        freestreamValue uniform 2.604e-05;
    }
    frontAndBack
    {
        type            empty;
    }
}
""")
        else:
            k_inf = 1.08493e-03
            omega_inf = 41.66
            with open(os.path.join(case_dir, "0", "k"), "w") as f:
                f.write(f"""FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      k;
}}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform {k_inf:.6e};
boundaryField
{{
    airfoil
    {{
        type            kqRWallFunction;
        value           uniform 1e-10;
    }}
    farfield
    {{
        type            freestream;
        freestreamValue uniform {k_inf:.6e};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
""")
            with open(os.path.join(case_dir, "0", "omega"), "w") as f:
                f.write(f"""FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      omega;
}}
dimensions      [0 0 -1 0 0 0 0];
internalField   uniform {omega_inf:.2f};
boundaryField
{{
    airfoil
    {{
        type            omegaWallFunction;
        value           uniform {omega_inf:.2f};
    }}
    farfield
    {{
        type            freestream;
        freestreamValue uniform {omega_inf:.2f};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
""")

    print(f"Setup complete: {case_dir}")
    return case_dir

if __name__ == "__main__":
    airfoil = sys.argv[1]
    model = sys.argv[2]
    alpha = float(sys.argv[3])
    prev = sys.argv[4] if len(sys.argv) > 4 else None
    setup_sweep_case(airfoil, model, alpha, prev)
