import streamlit as st
import sympy as sp

def find_equilibrium(equations, variables):
    # Convert strings to sympy expressions
    sym_vars = sp.symbols(variables)
    sym_eqns = [sp.sympify(eq.split('=')[1].strip()) for eq in equations]
    
    # Create the system of equations where each dX/dt = 0
    eqns_at_equilibrium = [sp.Eq(eq, 0) for eq in sym_eqns]
    
    # Solve the system of equations
    equilibrium_points = sp.solve(eqns_at_equilibrium, sym_vars, dict=True)
    
    return equilibrium_points

def equilibrium_page():
    st.title("Equilibrium Points Calculator for ODEs")
    st.write("Enter your system of differential equations in the format 'dX/dt = ...' for each equation. Use a new line for each equation.")

    # Text area for input
    equations_input = st.text_area("Enter the differential equations:", height=200)

    if st.button("Submit"):
        if equations_input.strip():
            # Split the input into individual equations
            equations_list = [eq.strip() for eq in equations_input.split('\n') if eq.strip()]
            
            # Extract variables from equations
            variables_set = set()
            for eq in equations_list:
                # Assumes the format 'dX/dt = ...'
                var = eq.split('=')[0].strip().split('/')[0][1:]
                variables_set.add(var)
            
            variables_list = list(variables_set)
            
            try:
                # Find equilibrium points
                equilibrium_points = find_equilibrium(equations_list, variables_list)
                
                # Display results
                st.write("The equilibrium points for the given set of equations are:")
                if isinstance(equilibrium_points, list) and equilibrium_points:
                    for point in equilibrium_points:
                        for var, expr in point.items():
                            st.latex(f"{sp.latex(var)}^* = {sp.latex(expr)}")
                else:
                    st.write("No equilibrium points found.")
            except Exception as e:
                st.error(f"An error occurred: {e}")
        else:
            st.error("Please enter at least one differential equation.")

def jacobian_page():
    st.title("Jacobian Matrix, Eigenvalues, and Eigenvectors Calculator")
    
    # Text area for inputting the differential equations
    equations_input = st.text_area("Enter the differential equations (e.g., 'dB/dt = ...'):", height=200)
    
    if 'equations' not in st.session_state:
        st.session_state.equations = ""
    if 'param_values' not in st.session_state:
        st.session_state.param_values = {}

    if st.button("Submit Equations"):
        if equations_input.strip():
            # Save equations to session state
            st.session_state.equations = equations_input.strip()
            
            # Split the input into individual equations
            equations_list = [eq.strip() for eq in st.session_state.equations.split('\n') if eq.strip()]
            
            # Extract variables from equations
            variables_set = set()
            for eq in equations_list:
                # Assumes the format 'dX/dt = ...'
                var = eq.split('=')[0].strip().split('/')[0][1:]
                variables_set.add(var)
            
            variables_list = list(variables_set)
            sym_vars = sp.symbols(variables_list)
            
            # Convert equations to sympy expressions
            sym_eqns = [sp.sympify(eq.split('=')[1].strip()) for eq in equations_list]
            F = sp.Matrix(sym_eqns)
            X = sp.Matrix(sym_vars)
            
            # Calculate the Jacobian matrix
            Jacobian = F.jacobian(X)
            st.write("Jacobian matrix:")
            st.latex(sp.latex(Jacobian))
            
            # Input fields for parameters
            st.write("Enter the values for the parameters:")
            param_values = {}
            param_names = list(Jacobian.free_symbols - set(sym_vars))
            for param in param_names:
                if param not in st.session_state.param_values:
                    st.session_state.param_values[param] = 0.0
                st.session_state.param_values[param] = st.number_input(f"Value for {param}", value=st.session_state.param_values[param])
            
            if st.button("Calculate Eigenvalues and Eigenvectors"):
                try:
                    # Evaluate the Jacobian matrix with parameter values
                    Jacobian_eval = Jacobian.subs(st.session_state.param_values)
                    st.write("Evaluated Jacobian matrix:")
                    st.latex(sp.latex(Jacobian_eval))
                    
                    # Calculate the eigenvalues and eigenvectors
                    eigenvals = Jacobian_eval.eigenvals()
                    eigenvects = Jacobian_eval.eigenvects()
                    
                    # Display eigenvalues
                    st.write("Eigenvalues:")
                    for val, multiplicity in eigenvals.items():
                        st.latex(f"Eigenvalue: {sp.latex(val)}, Multiplicity: {multiplicity}")
                    
                    # Display eigenvectors
                    st.write("Eigenvectors:")
                    for val, mult, vects in eigenvects:
                        st.latex(f"Eigenvalue: {sp.latex(val)}")
                        for vect in vects:
                            st.latex(f"Eigenvector: {sp.latex(vect)}")
                except Exception as e:
                    st.error(f"An error occurred while calculating eigenvalues and eigenvectors: {e}")
        else:
            st.error("Please enter at least one differential equation.")

def equilibrium():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Equilibrium Points Calculator", "Jacobian Matrix Calculator"])
    
    if page == "Equilibrium Points Calculator":
        equilibrium_page()
    elif page == "Jacobian Matrix Calculator":
        jacobian_page()

if __name__ == '__main__':
    equilibrium()
