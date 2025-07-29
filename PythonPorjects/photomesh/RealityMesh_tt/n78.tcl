set modelDir OneClick_output
set apExe P:/tools/blue/AddonPacker_64/AddonPacker_x64.exe
set vbsBlueVersion blue.trunk
set outputDir E:/VBS4/myData/Blue/content

set args " -v $vbsBlueVersion -s -severity debug -ap -ac -r -pfd  -exfi *.dep;*.log;*.pbo;*.ascii -t \"P:/temp\" -ld \"P:/export/$modelDir\" -i \"P:/vbs2/customer/structures/$modelDir\" -o \"$outputDir\""
puts "CMD> $apExe $args"
exec $apExe {*}$args

# Open input file.
brep_open world [lindex $argv 0]

# Save to output file.
world save [lindex $argv 1]
