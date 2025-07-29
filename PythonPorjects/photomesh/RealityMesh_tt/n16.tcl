# Delete Attributes Tcl
# Version 1.0
# 
# Copyright © 2014 TerraSim, Inc. All rights reserved.
#
# Description:
#
# This script will delete all attributes on input data that are not contained in the
# "attrKeep" list. This list contains all attributes you wish to retain on the input data.
#
# To use this script, add attributes you wish to keep between the curly braces after "set attrKeep".
# Then use an Apply Script node to run this script on input vector data.
#
# Change Log:
# 2014/6/20
# Created
#--------------------------------------------------------------------------
# Tcl TAV processing script
# lines beginning with "#" are comments

# Open input file.
brep_open world [lindex $argv 0]

# USER-EDITABLE LINE: List of attributes to keep, separated by spaces. Attributes with spaces in their names should
# be enclosed within quotes.
set attrKeep {name}

# Delete any attributes that are *not* in the above list.
proc attrDel {list type} {
	foreach attr [$type list "*"] {
		if {[lsearch $list $attr] == -1} {
			$type del $attr
		}
	}
}

# Apply procedure to areals.
world faceapply f {
	attrDel $attrKeep f
}

brep_dissolve world


# Save to output file.
world save [lindex $argv 1]
