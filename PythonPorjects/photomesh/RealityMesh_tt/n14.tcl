# Dissolve_areals.tcl
# Version 1.0
# 
# Copyright © 2012 TerraSim, Inc. All rights reserved.
#
# Description:
#
# This script dissolves areal features, which will turn multiple overlapping areals into a single feature.
#
# Change Log:
#
# 10/30/2012
# Created
#
#-------------------------------------------------------------------------
# Tcl BREP processing script
# lines beginning with "#" are comments

# Open input file.
brep_open world [lindex $argv 0]

# Delete all attribution, assign a common attribute to ensure full dissolve
# The brep_dissolve function requires like attribution for dissolving
world faceapply f {
    if { [f has *] } {
        f del -all *
		f set dissolve true
    }
}



# Delete all geometry not required to maintain attribution.
brep_dissolve world

# Save to output file.
world save [lindex $argv 1]

