import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
import sys
import numpy as np

def setup_case(airfoil, mesh_level, model, alpha_deg, cases_root, mesh_root):
    alpha_str = f"a{int(round(alpha_deg)):02d}"
    
    if mesh_level == "L1":
        case_dir = os.path.join(cases_root, f"{airfoil}_L1", model, alpha_str)
    else:
        case_dir = os.path.join(cases_root, airfoil, model, alpha_str)
        
    os.makedirs(case_dir, exist_ok=True)
    os.makedirs(os.path.join(case_dir, "constant"), exist_ok=True)
    os.makedirs(os.path.join(case_dir, "system"), exist_ok=True)
    os.makedirs(os.path.join(case_dir, "0"), exist_ok=True)

    # Clean old processor dirs, logs, and postProcessing
    for item in os.listdir(case_dir):
        if item.startswith("processor") or item.startswith("postProcessing") or item.startswith("log.") or item.endswith(".stdout"):
            p = os.path.join(case_dir, item)
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            else:
                os.remove(p)

    # 1. Mesh: copy polyMesh from mesh/<airfoil>/<level>/constant/polyMesh
    src_mesh = os.path.join(mesh_root, airfoil, mesh_level, "constant", "polyMesh")
    dst_mesh = os.path.join(case_dir, "constant", "polyMesh")
    os.makedirs(dst_mesh, exist_ok=True)
    for fname in ["points", "faces", "owner", "neighbour", "boundary"]:
        src_f = os.path.join(src_mesh, fname)
        dst_f = os.path.join(dst_mesh, fname)
        if not os.path.exists(dst_f):
            try:
                os.link(src_f, dst_f)
            except:
                import shutil
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

    # Section 7 iteration settings
    if alpha_deg >= 14.5:
        max_iter = 4000
        write_int = 1000
        relax_p = 0.2
        relax_u = 0.5
        relax_turb = 0.5
    else:
        max_iter = 2500
        write_int = 500
        relax_p = 0.3
        relax_u = 0.7
        relax_turb = 0.7

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
        writeInterval   1;
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
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,nuTilda) bounded Gauss linearUpwind default;
    div(phi,k)      bounded Gauss linearUpwind default;
    div(phi,omega)  bounded Gauss linearUpwind default;
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
    nNonOrthogonalCorrectors 0;
    consistent      yes;

    residualControl
    {{
        p               1e-05;
        U               1e-05;
        "(nuTilda|k|omega)" 1e-04;
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

    # 9. Fields in 0/
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
    nut_far = 2.604e-05
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
        type            fixedValue;
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
        # 0/nuTilda: freestream nutilda = 3 * nu = 2.604e-05
        with open(os.path.join(case_dir, "0", "nuTilda"), "w") as f:
            f.write(f"""FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nuTilda;
}}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 2.604e-05;
boundaryField
{{
    airfoil
    {{
        type            fixedValue;
        value           uniform 0;
    }}
    farfield
    {{
        type            freestream;
        freestreamValue uniform 2.604e-05;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
""")
    else:
        # SST: 0/k and 0/omega
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
internalField   uniform {omega_inf:.1f};
boundaryField
{{
    airfoil
    {{
        type            omegaWallFunction;
        value           uniform {omega_inf:.1f};
    }}
    farfield
    {{
        type            freestream;
        freestreamValue uniform {omega_inf:.1f};
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
    cases_root = os.path.join(PROJECT_ROOT, "cases")
    mesh_root = os.path.join(PROJECT_ROOT, "mesh")
    airfoil = sys.argv[1]
    mesh_level = sys.argv[2]
    model = sys.argv[3]
    alpha = float(sys.argv[4])
    setup_case(airfoil, mesh_level, model, alpha, cases_root, mesh_root)
